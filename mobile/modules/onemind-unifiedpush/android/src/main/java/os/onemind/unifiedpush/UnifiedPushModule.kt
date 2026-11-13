// SPDX-License-Identifier: Apache-2.0
package os.onemind.unifiedpush

import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.functions.Queues
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import org.unifiedpush.android.connector.UnifiedPush

/**
 * JS face of UnifiedPush. The app registers with the person's distributor (the ntfy app pointed at
 * the box's own ntfy), receives an endpoint URL, and gives that URL to the box
 * (`POST /v1/push/registrations`, contract §12.14). The box then POSTs a content-free ping
 * `{notification_id, box_id}` to it; the app fetches the text from the box over HTTPS.
 */
class UnifiedPushModule : Module() {
  private val context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()

  override fun definition() = ModuleDefinition {
    Name("OneMindUnifiedPush")

    Events(EVENT_ENDPOINT, EVENT_MESSAGE, EVENT_FAILED, EVENT_UNREGISTERED)

    // While JS listens, messages go to JS (which fetches the real text); otherwise the service
    // shows a content-free notification itself.
    OnStartObserving { Bridge.attach(this@UnifiedPushModule) }
    OnStopObserving { Bridge.detach(this@UnifiedPushModule) }
    OnDestroy { Bridge.detach(this@UnifiedPushModule) }

    /** Installed distributors (package names), e.g. the ntfy app. Empty: push cannot work yet. */
    Function("distributors") { UnifiedPush.getDistributors(context) }

    /** The distributor this app is registered with, if it acknowledged the registration. */
    Function("savedDistributor") { UnifiedPush.getAckDistributor(context) }

    Function("saveDistributor") { pkg: String -> UnifiedPush.saveDistributor(context, pkg) }

    /** Use the saved distributor, or the system default one (may show the distributor's picker). */
    AsyncFunction("useDefaultDistributor") { promise: Promise ->
      val activity = appContext.currentActivity
      if (activity == null) {
        promise.resolve(false)
        return@AsyncFunction
      }
      UnifiedPush.tryUseCurrentOrDefaultDistributor(activity) { ok -> promise.resolve(ok) }
    }.runOnQueue(Queues.MAIN)

    /** `vapid`: the box's VAPID public key (base64url, uncompressed P-256, 87 chars) or null. */
    Function("register") { vapid: String? ->
      UnifiedPush.register(context, INSTANCE, "OneMind alerts", vapid)
    }

    Function("unregister") {
      UnifiedPush.unregister(context, INSTANCE)
      Store.clear(context)
    }

    /** The last endpoint the distributor gave us (so JS does not miss one sent while it was not listening). */
    Function("lastEndpoint") { Store.endpoint(context) }
  }

  companion object {
    const val INSTANCE = "default"
    const val EVENT_ENDPOINT = "onNewEndpoint"
    const val EVENT_MESSAGE = "onMessage"
    const val EVENT_FAILED = "onRegistrationFailed"
    const val EVENT_UNREGISTERED = "onUnregistered"
  }
}
