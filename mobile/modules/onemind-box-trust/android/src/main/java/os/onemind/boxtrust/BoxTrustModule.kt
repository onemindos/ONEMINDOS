// SPDX-License-Identifier: Apache-2.0
package os.onemind.boxtrust

import android.util.Base64
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/** JS face of PinnedTrust (mobile/modules/onemind-box-trust/index.ts). */
class BoxTrustModule : Module() {
  private val context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()

  override fun definition() = ModuleDefinition {
    Name("OneMindBoxTrust")

    // Normally done earlier by BoxTrustPackage at Application.onCreate; a no-op then.
    OnCreate { PinnedTrust.install(context) }

    Function("pin") { caDer: String -> PinnedTrust.pin(context, Base64.decode(caDer, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)) }

    Function("clear") { PinnedTrust.clear(context) }

    Function("pinned") { PinnedTrust.pinnedSha256() }

    // Network: runs on the module's background queue, never the UI thread.
    AsyncFunction("probe") { url: String, timeoutMs: Int -> PinnedTrust.probe(url, timeoutMs.toLong()) }
  }
}
