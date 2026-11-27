// SPDX-License-Identifier: Apache-2.0
package os.onemind.location

import android.Manifest.permission.ACCESS_BACKGROUND_LOCATION
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
  private fun permission(background: Boolean): String =
    if (background && Build.VERSION.SDK_INT >= 29) ACCESS_BACKGROUND_LOCATION else ACCESS_COARSE_LOCATION

  override fun definition() = ModuleDefinition {
    Name("OneMindLocation")

    AsyncFunction("getPermission") { background: Boolean, promise: Promise ->
      Permissions.getPermissionsWithPermissionsManager(appContext.permissions, promise, permission(background))
    }

    AsyncFunction("requestPermission") { background: Boolean, promise: Promise ->
      val requested = if (background) arrayOf(permission(true))
      else arrayOf(ACCESS_COARSE_LOCATION, ACCESS_FINE_LOCATION)
      Permissions.askForPermissionsWithPermissionsManager(appContext.permissions, promise, *requested)
    }

    AsyncFunction("currentPosition") { background: Boolean, promise: Promise ->
      val context = appContext.reactContext ?: throw Exceptions.ReactContextLost()
      val permissions = appContext.permissions ?: throw Exceptions.PermissionsModuleNotFound()
      if (!permissions.hasGrantedPermissions(ACCESS_COARSE_LOCATION, permission(background))) {
        promise.reject("E_LOCATION_PERMISSION", "Location access is off.", null)
        return@AsyncFunction
      }
      val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
      val candidates = if (permissions.hasGrantedPermissions(ACCESS_FINE_LOCATION)) {
        listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
      } else {
        listOf(LocationManager.NETWORK_PROVIDER, "fused")
      }
      val provider = candidates.firstOrNull { it in manager.allProviders && manager.isProviderEnabled(it) }
      if (provider == null) {
        promise.reject("E_LOCATION_UNAVAILABLE", "The phone has no enabled location provider for this permission.", null)
        return@AsyncFunction
      }
      LocationManagerCompat.getCurrentLocation(manager, provider, CancellationSignal(), ContextCompat.getMainExecutor(context)) { fix ->
        if (fix == null) {
          promise.reject("E_LOCATION_UNAVAILABLE", "The phone could not find its location.", null)
        } else {
          promise.resolve(mapOf("latitude" to fix.latitude, "longitude" to fix.longitude,
            "accuracyMeters" to fix.accuracy.toDouble(), "timestamp" to fix.time.toDouble()))
        }
      }
    }
  }
}
