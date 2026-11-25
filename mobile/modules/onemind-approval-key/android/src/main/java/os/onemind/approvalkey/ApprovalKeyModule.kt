// SPDX-License-Identifier: Apache-2.0
package os.onemind.approvalkey

import android.content.pm.PackageManager
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyPermanentlyInvalidatedException
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import android.util.Base64
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_STRONG
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.functions.Queues
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * The phone's approval key (#703): an EC P-256 key in the Android Keystore that signs one approval.
 *
 * - StrongBox (a separate secure chip) when the phone has one, else the TEE.
 * - Authentication on every use: the key signs only inside a BiometricPrompt CryptoObject.
 * - BIOMETRIC_STRONG only: no PIN, pattern or password (no DEVICE_CREDENTIAL), so a destructive
 *   approval never accepts a passcode.
 * - Invalidated by a new enrolment: adding a finger or face kills the key; the app must enrol again.
 *
 * The private key never leaves the Keystore; JS only ever sees the public key and signatures.
 */
class ApprovalKeyModule : Module() {
  private val context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()

  private fun keyStore(): KeyStore = KeyStore.getInstance(STORE).apply { load(null) }

  private fun b64url(b: ByteArray) = Base64.encodeToString(b, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)

  private fun biometrics(): String =
    when (BiometricManager.from(context).canAuthenticate(BIOMETRIC_STRONG)) {
      BiometricManager.BIOMETRIC_SUCCESS -> "ok"
      BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED -> "none_enrolled"
      BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE -> "no_hardware"
      BiometricManager.BIOMETRIC_ERROR_SECURITY_UPDATE_REQUIRED -> "update_required"
      else -> "unavailable"
    }

  private fun strongBoxAvailable(): Boolean =
    Build.VERSION.SDK_INT >= 28 && context.packageManager.hasSystemFeature(PackageManager.FEATURE_STRONGBOX_KEYSTORE)

  private fun spec(strongBox: Boolean): KeyGenParameterSpec {
    val b = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
      .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
      .setDigests(KeyProperties.DIGEST_SHA256)
      .setUserAuthenticationRequired(true)
      .setInvalidatedByBiometricEnrollment(true)
    if (Build.VERSION.SDK_INT >= 30) {
      // 0 seconds = every single use needs its own authentication; strong biometrics only.
      b.setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
    } else {
      @Suppress("DEPRECATION")
      b.setUserAuthenticationValidityDurationSeconds(-1) // -1 = per use, biometric only
    }
    if (strongBox && Build.VERSION.SDK_INT >= 28) b.setIsStrongBoxBacked(true)
    return b.build()
  }

  /** "strongbox", "tee" or "software": where the Keystore says the key lives (reported, not attested). */
  private fun securityLevel(key: PrivateKey): String {
    val info = KeyFactory.getInstance(key.algorithm, STORE).getKeySpec(key, KeyInfo::class.java)
    if (Build.VERSION.SDK_INT >= 31) {
      return when (info.securityLevel) {
        KeyProperties.SECURITY_LEVEL_STRONGBOX -> "strongbox"
        KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT -> "tee"
        KeyProperties.SECURITY_LEVEL_UNKNOWN_SECURE -> "tee"
        else -> "software"
      }
    }
    @Suppress("DEPRECATION")
    return if (info.isInsideSecureHardware) "tee" else "software"
  }

  private fun publicKeyOrNull(): String? = keyStore().getCertificate(ALIAS)?.publicKey?.encoded?.let { b64url(it) }

  override fun definition() = ModuleDefinition {
    Name("OneMindApprovalKey")

    /** What this phone can do and whether a key exists. Never throws for a missing key. */
    Function("status") {
      mapOf(
        "biometrics" to biometrics(),
        "strongBoxAvailable" to strongBoxAvailable(),
        "publicKey" to publicKeyOrNull(),
      )
    }

    /** Makes a new key (replacing any old one). Returns its SubjectPublicKeyInfo (DER, base64url). */
    AsyncFunction("create") { promise: Promise ->
      val bio = biometrics()
      if (bio != "ok") {
        promise.reject("ERR_NO_BIOMETRIC", "strong biometrics are not set up on this phone ($bio)", null)
        return@AsyncFunction
      }
      keyStore().deleteEntry(ALIAS)
      val gen = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, STORE)
      val pair = try {
        gen.initialize(spec(strongBoxAvailable()))
        gen.generateKeyPair()
      } catch (e: StrongBoxUnavailableException) {
        gen.initialize(spec(false))
        gen.generateKeyPair()
      }
      promise.resolve(
        mapOf("publicKey" to b64url(pair.public.encoded), "securityLevel" to securityLevel(pair.private)),
      )
    }

    /**
     * Shows the system biometric prompt and, inside it, signs `payload` (UTF-8) with ECDSA SHA-256.
     * Resolves the DER signature (base64url); rejects ERR_CANCELLED, ERR_NO_KEY, ERR_KEY_INVALIDATED
     * (a new finger or face was added: the key is gone and the app must enrol again) or ERR_FAILED.
     */
    AsyncFunction("sign") { payload: String, title: String, subtitle: String, promise: Promise ->
      val activity = appContext.currentActivity as? FragmentActivity
      if (activity == null) {
        promise.reject("ERR_FAILED", "no foreground screen to show the prompt on", null)
        return@AsyncFunction
      }
      val ks = keyStore()
      val key = ks.getKey(ALIAS, null) as? PrivateKey
      if (key == null) {
        promise.reject("ERR_NO_KEY", "no approval key on this phone", null)
        return@AsyncFunction
      }
      val sig = Signature.getInstance("SHA256withECDSA")
      try {
        sig.initSign(key)
      } catch (e: KeyPermanentlyInvalidatedException) {
        ks.deleteEntry(ALIAS)
        promise.reject("ERR_KEY_INVALIDATED", "a new fingerprint or face was added; set up the approval key again", e)
        return@AsyncFunction
      }
      val info = BiometricPrompt.PromptInfo.Builder()
        .setTitle(title)
        .setSubtitle(subtitle)
        .setAllowedAuthenticators(BIOMETRIC_STRONG)
        .setNegativeButtonText("Cancel")
        .setConfirmationRequired(true)
        .build()
      val callback = object : BiometricPrompt.AuthenticationCallback() {
        override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
          val s = result.cryptoObject?.signature
          if (s == null) {
            promise.reject("ERR_FAILED", "the prompt returned no signing key", null)
            return
          }
          try {
            s.update(payload.toByteArray(Charsets.UTF_8))
            promise.resolve(b64url(s.sign()))
          } catch (e: Exception) {
            promise.reject("ERR_FAILED", "signing failed: ${e.javaClass.simpleName}", e)
          }
        }

        override fun onAuthenticationError(code: Int, msg: CharSequence) {
          val cancelled = code == BiometricPrompt.ERROR_USER_CANCELED ||
            code == BiometricPrompt.ERROR_NEGATIVE_BUTTON || code == BiometricPrompt.ERROR_CANCELED
          val lockout = code == BiometricPrompt.ERROR_LOCKOUT || code == BiometricPrompt.ERROR_LOCKOUT_PERMANENT
          promise.reject(if (cancelled) "ERR_CANCELLED" else if (lockout) "ERR_LOCKOUT" else "ERR_FAILED", msg.toString(), null)
        }
      }
      BiometricPrompt(activity, ContextCompat.getMainExecutor(activity), callback)
        .authenticate(info, BiometricPrompt.CryptoObject(sig))
    }.runOnQueue(Queues.MAIN)

    /** Deletes the key (the app also revokes it on the hub). */
    Function("remove") { keyStore().deleteEntry(ALIAS) }
  }

  companion object {
    private const val STORE = "AndroidKeyStore"
    private const val ALIAS = "onemind.approval.v1"
  }
}
