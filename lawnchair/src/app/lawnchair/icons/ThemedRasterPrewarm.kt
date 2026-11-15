package app.lawnchair.icons

import android.content.Context
import app.lawnchair.preferences.PreferenceManager
import com.android.launcher3.icons.ThemedIconDrawable
import com.android.launcher3.model.data.AppInfo
import com.android.launcher3.util.Executors.UI_HELPER_EXECUTOR

/**
 * Evergreen (SUI-7b): themed icons are drawn from a raster that is built on first draw (SUI-7).
 * Opening the drawer for the first time used to build one per app on the UI thread, in a single
 * frame. This builds the drawer's rasters in the background as soon as the apps are bound.
 */
object ThemedRasterPrewarm {

    /**
     * @param context the context the drawer icons are created with: it decides the colours.
     * @param size the drawer icon size in pixels.
     */
    @JvmStatic
    fun prewarmDrawer(context: Context, size: Int, apps: Array<AppInfo?>?) {
        if (apps.isNullOrEmpty() || size <= 0) return
        if (!PreferenceManager.getInstance(context).drawerThemedIcons.get()) return
        val infos = apps.mapNotNull { it?.bitmap }
        if (infos.isEmpty()) return
        // Same colours as BitmapInfo.newThemedIcon(context), resolved here on the UI thread.
        val colors = ThemedIconDrawable.getThemedColors(context)
        UI_HELPER_EXECUTOR.execute {
            infos.forEach { ThemedIconDrawable.prewarmRaster(it, size, colors) }
        }
    }
}
