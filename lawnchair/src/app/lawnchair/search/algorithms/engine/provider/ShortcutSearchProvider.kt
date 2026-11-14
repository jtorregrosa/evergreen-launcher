package app.lawnchair.search.algorithms.engine.provider

import android.content.Context
import android.content.pm.ShortcutInfo
import android.os.SystemClock
import app.lawnchair.launcher
import app.lawnchair.search.algorithms.engine.SearchResult
import app.lawnchair.util.isDefaultLauncher
import com.android.launcher3.model.data.AppInfo
import com.android.launcher3.popup.PopupPopulator
import com.android.launcher3.shortcuts.ShortcutRequest

object ShortcutSearchProvider {
    // Evergreen: isDefaultLauncher() is a resolveActivity IPC; avoid repeating it per keystroke.
    private const val DEFAULT_LAUNCHER_CACHE_MS = 30_000L

    @Volatile private var isDefaultCached = false

    @Volatile private var isDefaultCheckedAt = 0L

    private fun isDefaultLauncherCached(context: Context): Boolean {
        val now = SystemClock.elapsedRealtime()
        if (isDefaultCheckedAt == 0L || now - isDefaultCheckedAt > DEFAULT_LAUNCHER_CACHE_MS) {
            isDefaultCached = context.isDefaultLauncher()
            isDefaultCheckedAt = now
        }
        return isDefaultCached
    }

    fun search(context: Context, appResults: List<SearchResult.App>): List<SearchResult.Shortcut> {
        if (appResults.size == 1 && isDefaultLauncherCached(context)) {
            val singleApp = appResults.first().data
            val shortcuts = getShortcuts(singleApp, context)
            return shortcuts.map { SearchResult.Shortcut(data = it) }
        }
        return emptyList()
    }

    private fun getShortcuts(app: AppInfo, context: Context): List<ShortcutInfo> {
        val shortcuts = ShortcutRequest(context.launcher, app.user)
            .withContainer(app.targetComponent)
            .query(ShortcutRequest.PUBLISHED)
        return PopupPopulator.sortAndFilterShortcuts(shortcuts)
    }
}
