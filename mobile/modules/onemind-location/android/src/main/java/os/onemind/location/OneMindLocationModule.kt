// SPDX-License-Identifier: Apache-2.0
package os.onemind.location

import android.Manifest.permission.ACCESS_COARSE_LOCATION
import android.Manifest.permission.ACCESS_FINE_LOCATION
import android.content.Context
import android.location.LocationManager
import android.os.Build
import android.os.CancellationSignal
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import expo.modules.interfaces.permissions.Permissions
import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class OneMindLocationModule : Module() {
  private val unavailable = mapOf("granted" to false, "canAskAgain" to false, "status" to "unavailable")

  override fun definition() = ModuleDefinition {
    Name("OneMindLocation")

    AsyncFunction("getPermission") { background: Boolean, promise: Promise ->
      if (background) promise.resolve(unavailable)
      else Permissions.getPermissionsWithPermissionsManager(appContext.permissions, promise, ACCESS_COARSE_LOCATION)
    }

    AsyncFunction("requestPermission") { background: Boolean, promise: Promise ->
      if (background) promise.resolve(unavailable)
      else Permissions.askForPermissionsWithPermissionsManager(appContext.permissions, promise, ACCESS_COARSE_LOCATION, ACCESS_FINE_LOCATION)
    }

    AsyncFunction("currentPosition") { background: Boolean, promise: Promise ->
      if (background) {
        promise.reject("E_LOCATION_UNAVAILABLE", "Background location is not available.", null)
        return@AsyncFunction
      }
      val context = appContext.reactContext ?: throw Exceptions.ReactContextLost()
      val permissions = appContext.permissions ?: throw Exceptions.PermissionsModuleNotFound()
      if (!permissions.hasGrantedPermissions(ACCESS_COARSE_LOCATION)) {
        promise.reject("E_LOCATION_PERMISSION", "Location access is off.", null)
        return@AsyncFunction
      }
      val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
      val candidates = if (permissions.hasGrantedPermissions(ACCESS_FINE_LOCATION)) {
        buildList {
          if (Build.VERSION.SDK_INT >= 31) add(LocationManager.FUSED_PROVIDER)
          add(LocationManager.GPS_PROVIDER)
          add(LocationManager.NETWORK_PROVIDER)
        }
      } else {
        listOf(LocationManager.NETWORK_PROVIDER, "fused")
      }
      val providers = candidates.filter { it in manager.allProviders && manager.isProviderEnabled(it) }.iterator()
      val mainExecutor = ContextCompat.getMainExecutor(context)
      fun tryNextProvider() {
        if (!providers.hasNext()) {
          promise.reject("E_LOCATION_UNAVAILABLE", "The phone could not find its location.", null)
          return
        }
        LocationManagerCompat.getCurrentLocation(manager, providers.next(), CancellationSignal(), mainExecutor) { fix ->
          if (fix == null) {
            tryNextProvider()
          } else {
            promise.resolve(mapOf("latitude" to fix.latitude, "longitude" to fix.longitude,
              "accuracyMeters" to fix.accuracy.toDouble(), "timestamp" to fix.time.toDouble()))
          }
        }
      }
      tryNextProvider()
    }
  }
}
