// SPDX-License-Identifier: Apache-2.0
package os.onemind.unifiedpush

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.drawable.Icon
import android.net.Uri
import android.os.Build
import androidx.annotation.RequiresApi

/**
 * Notifications this module shows itself (issue #704). Approval notifications carry two buttons,
 * Review and Deny, and both need the phone unlocked (setAuthenticationRequired, Android 12+).
 * Approve is never a notification button. The buttons only open app links; the app asks for its
 * own unlock again before a Deny is recorded (src/lock/NotificationActions.tsx).
 */
internal object Notices {
  private const val CHANNEL = "hub"
  private val ID = Regex("^[A-Za-z0-9_-]{1,64}$")

  fun validId(v: String?): String? = v?.takeIf { it.matches(ID) }

  /** The manager, or null when this app's notifications are off. */
  private fun manager(context: Context): NotificationManager? {
    val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    if (Build.VERSION.SDK_INT >= 24 && !nm.areNotificationsEnabled()) return null
    if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CHANNEL) == null) {
      nm.createNotificationChannel(NotificationChannel(CHANNEL, "Hub activity", NotificationManager.IMPORTANCE_HIGH))
    }
    return nm
  }

  private fun link(context: Context, uri: String): PendingIntent {
    val open = Intent(Intent.ACTION_VIEW, Uri.parse(uri)).setPackage(context.packageName).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    return PendingIntent.getActivity(context, uri.hashCode(), open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
  }

  /** A button that opens `uri` only after the person unlocks the phone. */
  @RequiresApi(Build.VERSION_CODES.S)
  private fun lockedAction(context: Context, title: String, uri: String): Notification.Action {
    return Notification.Action.Builder(Icon.createWithResource(context, R.drawable.onemind_notification), title, link(context, uri))
      .setAuthenticationRequired(true)
      .build()
  }

  @Suppress("DEPRECATION")
  private fun builder(context: Context): Notification.Builder =
    if (Build.VERSION.SDK_INT >= 26) Notification.Builder(context, CHANNEL) else Notification.Builder(context)

  /** Text the box wrote stays off the lock screen; the lock screen shows only that a request waits. */
  private fun publicVersion(context: Context, text: String): Notification =
    builder(context).setSmallIcon(R.drawable.onemind_notification).setContentTitle("OneMind").setContentText(text).build()

  /** App closed: say only that something is new, with Review and Deny (the app checks it is a request). */
  fun showOpaque(context: Context, id: String?) {
    val nm = manager(context) ?: return
    val open = if (id != null) "onemind://inbox?id=$id" else "onemind://inbox"
    val b = builder(context).setSmallIcon(R.drawable.onemind_notification)
      .setContentTitle("OneMind")
      .setContentText("Something new on your box. Open the app to see it.")
      .setContentIntent(link(context, open))
      .setAutoCancel(true)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && id != null) {
      b.addAction(lockedAction(context, "Review", "onemind://approvals?review_notification=$id"))
      b.addAction(lockedAction(context, "Deny", "onemind://approvals?deny_notification=$id"))
    }
    nm.notify(id ?: "onemind", 1, b.build())
  }

  /** App running: an approval request with the text the app fetched from the box over HTTPS. */
  fun showApproval(context: Context, tag: String, title: String, body: String, actionId: String) {
    val action = validId(actionId) ?: return
    val nm = manager(context) ?: return
    val review = "onemind://approvals?review=$action"
    val b = builder(context).setSmallIcon(R.drawable.onemind_notification)
      .setContentTitle(title)
      .setContentText(body)
      .setContentIntent(link(context, review))
      .setVisibility(Notification.VISIBILITY_PRIVATE)
      .setPublicVersion(publicVersion(context, "Approval needed. Unlock to review."))
      .setAutoCancel(true)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
      b.addAction(lockedAction(context, "Review", review))
      b.addAction(lockedAction(context, "Deny", "onemind://approvals?deny=$action"))
    }
    nm.notify(tag, 1, b.build())
  }
}
