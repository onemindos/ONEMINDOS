// SPDX-License-Identifier: Apache-2.0
package os.onemind.unifiedpush

import android.content.Context
import org.json.JSONObject
import org.unifiedpush.android.connector.FailedReason
import org.unifiedpush.android.connector.PushService
import org.unifiedpush.android.connector.data.PushEndpoint
import org.unifiedpush.android.connector.data.PushMessage
import java.lang.ref.WeakReference

/** Holds the module while JS listens, so the service can hand events to JS. */
internal object Bridge {
  private var ref: WeakReference<UnifiedPushModule>? = null

  @Synchronized fun attach(m: UnifiedPushModule) {
    ref = WeakReference(m)
  }

  @Synchronized fun detach(m: UnifiedPushModule) {
    if (ref?.get() === m) ref = null
  }

  /** True when a JS listener received the event. */
  @Synchronized fun emit(name: String, body: Map<String, Any?>): Boolean {
    val m = ref?.get() ?: return false
    return try {
      m.sendEvent(name, body)
      true
    } catch (e: Exception) {
      false
    }
  }
}

/** The endpoint is a capability URL on the person's own ntfy; it stays in app-private storage. */
internal object Store {
  private const val PREFS = "onemind.unifiedpush"

  fun save(context: Context, url: String, p256dh: String?, auth: String?, temporary: Boolean) {
    context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
      .putString("url", url).putString("p256dh", p256dh).putString("auth", auth).putBoolean("temporary", temporary)
      .apply()
  }

  fun endpoint(context: Context): Map<String, Any?>? {
    val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    val url = p.getString("url", null) ?: return null
    return mapOf("url" to url, "p256dh" to p.getString("p256dh", null), "auth" to p.getString("auth", null), "temporary" to p.getBoolean("temporary", false))
  }

  fun clear(context: Context) {
    context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().apply()
  }

  /** Only the time a ping arrived, so Settings can show it even when the app was closed. */
  fun savePing(context: Context, at: Long) {
    context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putLong("ping", at).apply()
  }

  fun lastPing(context: Context): Double? =
    context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getLong("ping", 0L).takeIf { it > 0L }?.toDouble()
}

class OneMindPushService : PushService() {
  override fun onNewEndpoint(endpoint: PushEndpoint, instance: String) {
    val keys = endpoint.pubKeySet
    Store.save(this, endpoint.url, keys?.pubKey, keys?.auth, endpoint.temporary)
    Bridge.emit(
      UnifiedPushModule.EVENT_ENDPOINT,
      mapOf("url" to endpoint.url, "p256dh" to keys?.pubKey, "auth" to keys?.auth, "temporary" to endpoint.temporary),
    )
  }

  override fun onMessage(message: PushMessage, instance: String) {
    // The box sends only ids (D-005). Anything else is ignored rather than shown.
    val id = parseId(message.content.toString(Charsets.UTF_8))
    Store.savePing(this, System.currentTimeMillis())
    if (!Bridge.emit(UnifiedPushModule.EVENT_MESSAGE, mapOf("id" to id))) showOpaque(this, id)
  }

  override fun onRegistrationFailed(reason: FailedReason, instance: String) {
    Bridge.emit(UnifiedPushModule.EVENT_FAILED, mapOf("reason" to reason.name))
  }

  override fun onUnregistered(instance: String) {
    Store.clear(this)
    Bridge.emit(UnifiedPushModule.EVENT_UNREGISTERED, emptyMap())
  }

  companion object {
    /** `{"notification_id": "ntf_…", "box_id": "…"}` (or `opaque_id`) → the id, if it looks like one. */
    fun parseId(text: String): String? = try {
      val o = JSONObject(text)
      val v = o.optString("notification_id").ifEmpty { o.optString("opaque_id") }
      v.takeIf { it.matches(Regex("^[A-Za-z0-9_-]{1,64}$")) }
    } catch (e: Exception) {
      null
    }

    /** App closed: say only that something is new (Notices adds Review and Deny, both behind an unlock). */
    fun showOpaque(context: Context, id: String?) = Notices.showOpaque(context, id)
  }
}
