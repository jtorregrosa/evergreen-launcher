package app.lawnchair.evergreen

import android.content.Context
import android.util.Log
import androidx.core.content.edit
import app.lawnchair.preferences.PreferenceManager
import com.android.launcher3.LauncherPrefs
import java.io.File

/**
 * Evergreen: gives tablets a 6-column home screen grid and a 6-icon dock by default.
 *
 * The grid size lives in user preferences (`pref_workspaceColumns`, `pref_workspaceRows`,
 * `pref_hotseatColumns`) whose built-in defaults (4x5, dock 4) are phone sized. Those values
 * also name the launcher database (`launcher_<rows>_<columns>_<hotseat>.db`), so changing the
 * defaults alone would open an empty database at the next cold start and reset the home screen.
 *
 * This runs once per install, before the device profile is created:
 * - only on tablets (smallest width >= 600 dp) where the user never chose a grid;
 * - it stores the tablet values as explicit preferences;
 * - an existing database is renamed to the new name, so the layout is kept as it is: a wider
 *   grid with the same rows needs no item moves, and the dock keeps 6 slots, which is what
 *   tablets used before Evergreen detected them correctly on Android 10;
 * - the stored grid state is updated to match, so the model sees no grid change to migrate.
 */
object TabletGridDefaults {

    private const val TAG = "TabletGridDefaults"
    private const val DONE_KEY = "evergreen_tablet_grid_defaults_v1"
    private const val KEY_COLUMNS = "pref_workspaceColumns"
    private const val KEY_ROWS = "pref_workspaceRows"
    private const val KEY_HOTSEAT = "pref_hotseatColumns"

    const val TABLET_COLUMNS = 6
    const val TABLET_HOTSEAT = 6

    fun apply(context: Context) {
        val prefs = PreferenceManager.getInstance(context)
        val sp = prefs.sp
        if (sp.getBoolean(DONE_KEY, false)) return
        try {
            migrate(context, prefs)
        } catch (t: Throwable) {
            Log.e(TAG, "Could not apply the tablet grid defaults", t)
        }
        sp.edit { putBoolean(DONE_KEY, true) }
    }

    private fun migrate(context: Context, prefs: PreferenceManager) {
        val sp = prefs.sp
        if (context.resources.configuration.smallestScreenWidthDp < 600) return
        if (sp.contains(KEY_COLUMNS) || sp.contains(KEY_ROWS) || sp.contains(KEY_HOTSEAT)) return

        val rows = prefs.workspaceRows.get()
        val oldName = "launcher_${rows}_${prefs.workspaceColumns.get()}_${prefs.hotseatColumns.get()}.db"
        val newName = "launcher_${rows}_${TABLET_COLUMNS}_$TABLET_HOTSEAT.db"
        val oldDb = context.getDatabasePath(oldName)
        val newDb = context.getDatabasePath(newName)

        if (oldDb.exists() && !newDb.exists()) {
            // Rename the database together with its journal or WAL files.
            for (suffix in listOf("", "-journal", "-wal", "-shm")) {
                val from = File(oldDb.path + suffix)
                if (from.exists() && !from.renameTo(File(newDb.path + suffix))) {
                    Log.e(TAG, "Could not rename $from, keeping the phone grid")
                    return
                }
            }
            LauncherPrefs.get(context).putSync(
                LauncherPrefs.DB_FILE.to(newName),
                LauncherPrefs.WORKSPACE_SIZE.to("$TABLET_COLUMNS,$rows"),
                LauncherPrefs.HOTSEAT_COUNT.to(TABLET_HOTSEAT),
            )
        } else if (oldDb.exists() || newDb.exists()) {
            // Unexpected files: leave the grid alone rather than risk the user's layout.
            return
        }

        // Written directly: the preference objects' change listeners reload the grid, and
        // nothing is loaded yet.
        sp.edit(commit = true) {
            putInt(KEY_COLUMNS, TABLET_COLUMNS)
            putInt(KEY_HOTSEAT, TABLET_HOTSEAT)
        }
        Log.i(TAG, "Tablet grid defaults applied, database $oldName -> $newName")
    }
}
