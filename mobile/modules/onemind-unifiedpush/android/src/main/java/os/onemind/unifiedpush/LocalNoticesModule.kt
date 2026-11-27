// SPDX-License-Identifier: Apache-2.0
package os.onemind.unifiedpush

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import expo.modules.interfaces.permissions.Permissions
import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class LocalNoticesModule : Module() {
  private val context
    get() = appContext.reactContext ?: throw Exceptions.ReactContextLost()
  private val manager
    get() = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

  override fun definition() = ModuleDefinition {
    Name("OneMindLocalNotices")

    AsyncFunction("getPermission") { promise: Promise -> permission(false, promise) }
    AsyncFunction("requestPermission") { promise: Promise -> permission(true, promise) }

    AsyncFunction("show") { id: String, title: String, body: String, route: String ->
      if (!manager.areNotificationsEnabled()) return@AsyncFunction
      val destination = route.takeIf { it in destinations } ?: "inbox"
      val link = Uri.Builder().scheme("onemind").authority(destination).build()
      val open = Intent(Intent.ACTION_VIEW, link).setPackage(context.packageName).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
      val pending = PendingIntent.getActivity(context, id.hashCode(), open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
      if (Build.VERSION.SDK_INT >= 26 && manager.getNotificationChannel(channel) == null) {
        manager.createNotificationChannel(NotificationChannel(channel, "Hub activity", NotificationManager.IMPORTANCE_HIGH))
      }
      @Suppress("DEPRECATION")
      val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(context, channel) else Notification.Builder(context)
      val notification = builder.setSmallIcon(context.applicationInfo.icon)
        .setContentTitle(title).setContentText(body).setStyle(Notification.BigTextStyle().bigText(body))
        .setContentIntent(pending).setAutoCancel(true).build()
      manager.notify(id, 1, notification)
    }
  }

  private fun permission(ask: Boolean, promise: Promise) {
    if (Build.VERSION.SDK_INT < 33) {
      val allowed = manager.areNotificationsEnabled()
      val status = if (allowed) "granted" else "denied"
      promise.resolve(mapOf("granted" to allowed, "canAskAgain" to false, "status" to status))
    } else if (ask) {
      Permissions.askForPermissionsWithPermissionsManager(appContext.permissions, promise, Manifest.permission.POST_NOTIFICATIONS)
    } else {
      Permissions.getPermissionsWithPermissionsManager(appContext.permissions, promise, Manifest.permission.POST_NOTIFICATIONS)
    }
  }

  private companion object {
    const val channel = "hub"
    val destinations = setOf("approvals", "nodes", "activity", "inbox")
  }
}
