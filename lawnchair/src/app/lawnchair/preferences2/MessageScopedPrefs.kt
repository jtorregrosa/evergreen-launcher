package app.lawnchair.preferences2

import android.os.Handler
import android.os.Looper
import com.patrykmichalik.opto.core.firstBlocking
import com.patrykmichalik.opto.domain.Preference

/**
 * Evergreen (EVG-3g): preference reads memoized for the current main-thread message only.
 *
 * `firstBlocking()` costs about 0.3 ms per call on the TB-X606F (a `runBlocking` event loop plus
 * the exception `first()` uses to stop the flow). A cold start builds four `DeviceProfile`s in
 * one message, each reading about 17 preferences. They now share one read per preference.
 *
 * Unlike `PreferenceManager2.cachedValue()`, which is updated asynchronously and can briefly
 * return an old value after a write, this cache is cleared before the next main-thread message
 * runs. A preference change (from Settings or a listener) is always handled in a later message,
 * so it is read fresh. Off the main thread it falls back to `firstBlocking()`.
 */
object MessageScopedPrefs {
    private val mainLooper = Looper.getMainLooper()
    private val handler = Handler(mainLooper)
    private val values = HashMap<Preference<*, *, *>, Any?>()
    private var clearPosted = false
    private val clear = Runnable {
        values.clear()
        clearPosted = false
    }

    @JvmStatic
    fun <C> get(pref: Preference<C, *, *>): C {
        if (Looper.myLooper() != mainLooper) return pref.firstBlocking()
        if (values.containsKey(pref)) {
            @Suppress("UNCHECKED_CAST")
            return values[pref] as C
        }
        val value = pref.firstBlocking()
        values[pref] = value
        if (!clearPosted) {
            clearPosted = true
            handler.postAtFrontOfQueue(clear)
        }
        return value
    }
}
