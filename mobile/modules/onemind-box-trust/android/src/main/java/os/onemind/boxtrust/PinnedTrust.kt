// SPDX-License-Identifier: Apache-2.0
package os.onemind.boxtrust

import android.content.Context
import android.util.Base64
import com.facebook.react.modules.network.OkHttpClientFactory
import com.facebook.react.modules.network.OkHttpClientProvider
import java.io.ByteArrayInputStream
import java.io.IOException
import java.security.KeyStore
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager
import okhttp3.OkHttpClient
import okhttp3.Request

/**
 * The one box CA this phone paired with, trusted by the app's own HTTPS (React Native fetch, OkHttp)
 * and by nothing else on the phone. The system CAs are always tried first; the pinned CA is used only
 * when they refuse a chain, and only that CA (no other user CA). Host names are still checked by OkHttp.
 * The CA certificate is public data (the box serves it openly at /v1/tls/ca.crt), so it is kept in this
 * app's private preferences, not in the keystore.
 */
object PinnedTrust {
  private const val PREFS = "onemind.boxtrust"
  private const val KEY = "ca_der"
  private const val MAX_CA_BYTES = 64 * 1024

  @Volatile private var pinned: X509Certificate? = null
  @Volatile private var installed = false

  private val system: X509TrustManager by lazy { trustManagerFor(null) }

  private fun trustManagerFor(ks: KeyStore?): X509TrustManager {
    val f = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
    f.init(ks)
    return f.trustManagers.filterIsInstance<X509TrustManager>().first()
  }

  private fun certFrom(der: ByteArray): X509Certificate =
    CertificateFactory.getInstance("X.509").generateCertificate(ByteArrayInputStream(der)) as X509Certificate

  private fun onlyThis(ca: X509Certificate): X509TrustManager {
    val ks = KeyStore.getInstance(KeyStore.getDefaultType()).apply {
      load(null, null)
      setCertificateEntry("onemind-box", ca)
    }
    return trustManagerFor(ks)
  }

  private fun authTypeFor(leaf: X509Certificate) = if (leaf.publicKey.algorithm == "RSA") "ECDHE_RSA" else "ECDHE_ECDSA"

  fun sha256Hex(b: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

  val trustManager: X509TrustManager = object : X509TrustManager {
    override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = system.checkClientTrusted(chain, authType)

    override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
      try {
        system.checkServerTrusted(chain, authType)
      } catch (e: CertificateException) {
        val ca = pinned ?: throw e
        onlyThis(ca).checkServerTrusted(chain, authType)
      }
    }

    override fun getAcceptedIssuers(): Array<X509Certificate> = system.acceptedIssuers + listOfNotNull(pinned)
  }

  private fun prefs(c: Context) = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

  /** At app start, before React Native makes its HTTP client. */
  @Synchronized
  fun install(context: Context) {
    if (installed) return
    installed = true
    prefs(context).getString(KEY, null)?.let { b64 ->
      pinned = runCatching { certFrom(Base64.decode(b64, Base64.NO_WRAP)) }.getOrNull()
    }
    val app = context.applicationContext
    OkHttpClientProvider.setOkHttpClientFactory(OkHttpClientFactory {
      val ssl = SSLContext.getInstance("TLS").apply { init(null, arrayOf<TrustManager>(trustManager), null) }
      OkHttpClientProvider.createClientBuilder(app).sslSocketFactory(ssl.socketFactory, trustManager).build()
    })
  }

  fun pin(context: Context, der: ByteArray) {
    val ca = certFrom(der)
    if (ca.basicConstraints < 0) throw CertificateException("not a CA certificate")
    prefs(context).edit().putString(KEY, Base64.encodeToString(der, Base64.NO_WRAP)).apply()
    pinned = ca
  }

  fun clear(context: Context) {
    prefs(context).edit().remove(KEY).apply()
    pinned = null
  }

  fun pinnedSha256(): String? = pinned?.let { sha256Hex(it.encoded) }

  /**
   * Fetch `<url>/v1/tls/ca.crt` without trusting the address yet (the chain is only recorded), then check
   * that the recorded chain verifies to the CA it served. JS compares the CA's sha256 with the join QR;
   * only a match is ever pinned. Nothing but this GET is sent.
   */
  fun probe(url: String, timeoutMs: Long): Map<String, Any> {
    if (!url.startsWith("https://")) throw IOException("only https addresses are probed")
    var seen: Array<X509Certificate>? = null
    val record = object : X509TrustManager {
      override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = throw CertificateException("no client certificates")
      override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
        if (chain.isEmpty()) throw CertificateException("empty chain")
        seen = chain
      }
      override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
    }
    val ssl = SSLContext.getInstance("TLS").apply { init(null, arrayOf<TrustManager>(record), null) }
    val client = OkHttpClient.Builder()
      .sslSocketFactory(ssl.socketFactory, record)
      .callTimeout(timeoutMs, TimeUnit.MILLISECONDS)
      .followRedirects(false)
      .followSslRedirects(false)
      .build()
    val req = Request.Builder().url("$url/v1/tls/ca.crt").header("Accept", "application/x-x509-ca-cert").build()
    val der = client.newCall(req).execute().use { r ->
      if (!r.isSuccessful) throw IOException("HTTP ${r.code}")
      val src = r.body?.source() ?: throw IOException("empty answer")
      if (src.request((MAX_CA_BYTES + 1).toLong())) throw IOException("answer too large for a certificate")
      src.buffer.readByteArray()
    }
    val chain = seen ?: throw IOException("no TLS chain seen")
    val chainOk = runCatching { onlyThis(certFrom(der)).checkServerTrusted(chain, authTypeFor(chain[0])) }.isSuccess
    return mapOf(
      "servedCa" to sha256Hex(der),
      "chainOk" to chainOk,
      "caDer" to Base64.encodeToString(der, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING),
    )
  }
}
