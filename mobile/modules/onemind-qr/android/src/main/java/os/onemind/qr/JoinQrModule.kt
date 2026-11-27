// SPDX-License-Identifier: Apache-2.0
package os.onemind.qr

import android.graphics.BitmapFactory
import android.net.Uri
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.RGBLuminanceSource
import com.google.zxing.ReaderException
import com.google.zxing.common.HybridBinarizer
import com.google.zxing.qrcode.QRCodeReader
import expo.modules.kotlin.exception.Exceptions
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.io.File

class JoinQrModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("OneMindJoinQr")
    AsyncFunction("readCameraPhoto") { uri: String ->
      val context = appContext.reactContext ?: throw Exceptions.ReactContextLost()
      val location = Uri.parse(uri)
      require(location.scheme == "file") { "Expected a camera photo file." }
      val path = File(requireNotNull(location.path)).canonicalFile
      val cache = context.cacheDir.canonicalFile
      require(path.path.startsWith(cache.path + File.separator) && path.isFile) { "Expected an app-cache camera photo." }

      val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
      BitmapFactory.decodeFile(path.path, options)
      var scale = 1
      val side = maxOf(options.outWidth, options.outHeight)
      while (side / scale > 1600) scale *= 2
      options.inJustDecodeBounds = false
      options.inSampleSize = scale
      val bitmap = BitmapFactory.decodeFile(path.path, options) ?: return@AsyncFunction null
      try {
        val pixels = IntArray(bitmap.width * bitmap.height)
        bitmap.getPixels(pixels, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
        val image = BinaryBitmap(HybridBinarizer(RGBLuminanceSource(bitmap.width, bitmap.height, pixels)))
        QRCodeReader().decode(image, mapOf(DecodeHintType.TRY_HARDER to true)).text
      } catch (_: ReaderException) {
        null
      } finally {
        bitmap.recycle()
      }
    }
  }
}
