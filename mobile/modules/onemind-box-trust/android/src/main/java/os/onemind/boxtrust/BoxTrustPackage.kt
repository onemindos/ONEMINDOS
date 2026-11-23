// SPDX-License-Identifier: Apache-2.0
package os.onemind.boxtrust

import android.app.Application
import android.content.Context
import expo.modules.core.interfaces.ApplicationLifecycleListener
import expo.modules.core.interfaces.Package

/** Installs the pinned-trust HTTP client factory at Application.onCreate, before React Native makes its client. */
class BoxTrustPackage : Package {
  override fun createApplicationLifecycleListeners(context: Context): List<ApplicationLifecycleListener> =
    listOf(object : ApplicationLifecycleListener {
      override fun onCreate(application: Application) = PinnedTrust.install(application)
    })
}
