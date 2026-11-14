package app.lawnchair

import android.annotation.SuppressLint
import android.appwidget.AppWidgetHost
import android.appwidget.AppWidgetHostView
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProviderInfo
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import androidx.core.content.edit
import com.android.launcher3.Utilities
import com.android.launcher3.util.MainThreadInitializedObject
import com.android.launcher3.util.SafeCloseable
import kotlinx.coroutines.CoroutineName
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.flow.onStart
import kotlinx.coroutines.flow.shareIn
import kotlinx.coroutines.plus

class HeadlessWidgetsManager(private val context: Context) : SafeCloseable {

    private val scope = MainScope() + CoroutineName("HeadlessWidgetsManager")
    private val prefs = Utilities.getDevicePrefs(context)
    private val widgetManager = AppWidgetManager.getInstance(context)
    private val host = HeadlessAppWidgetHost(context)
    private val widgetsMap = mutableMapOf<String, Widget>()

    private var listening = false

    init {
        setListening(true)
    }

    /**
     * Evergreen: the host used to listen forever, so RemoteViews updates (search bar, At a Glance)
     * were inflated and measured while the launcher was in the background. The launcher now
     * toggles this from onStart/onStop; startListening() re-delivers pending updates.
     */
    fun setListening(listen: Boolean) {
        if (listen == listening) return
        listening = listen
        runCatching { if (listen) host.startListening() else host.stopListening() }
    }

    fun getWidget(info: AppWidgetProviderInfo, prefKey: String): Widget {
        val widget = widgetsMap.getOrPut(prefKey) { Widget(info, prefKey) }
        check(info.provider == widget.info.provider) {
            "widget $prefKey was created with a different provider"
        }
        return widget
    }

    fun subscribeUpdates(info: AppWidgetProviderInfo, prefKey: String): Flow<AppWidgetHostView> {
        val widget = getWidget(info, prefKey)
        if (!widget.isBound) {
            return emptyFlow()
        }
        return widget.updates
    }

    override fun close() {
        TODO("Not yet implemented")
    }

    private class HeadlessAppWidgetHost(context: Context) : AppWidgetHost(context, 1028) {

        override fun onCreateView(
            context: Context,
            appWidgetId: Int,
            appWidget: AppWidgetProviderInfo?,
        ): AppWidgetHostView {
            return HeadlessAppWidgetHostView(context)
        }
    }

    @SuppressLint("ViewConstructor")
    private class HeadlessAppWidgetHostView(context: Context) : AppWidgetHostView(context) {

        var updateCallback: ((view: AppWidgetHostView) -> Unit)? = null

        override fun updateAppWidget(remoteViews: RemoteViews?) {
            super.updateAppWidget(remoteViews)

            updateCallback?.invoke(this)
        }
    }

    inner class Widget internal constructor(val info: AppWidgetProviderInfo, private val prefKey: String) {

        private var widgetId = prefs.getInt(prefKey, -1)
        val isBound: Boolean
            get() = widgetManager.getAppWidgetInfo(widgetId)?.provider == info.provider
        val updates = callbackFlow {
            val view = host.createView(context, widgetId, info) as HeadlessAppWidgetHostView
            trySend(view)
            view.updateCallback = { trySend(it) }
            awaitClose()
        }
            .onStart { if (!isBound) throw WidgetNotBoundException() }
            .shareIn(
                scope,
                SharingStarted.WhileSubscribed(),
                replay = 1,
            )

        init {
            bind()
        }

        fun bind() {
            if (!isBound) {
                if (widgetId > -1) {
                    host.deleteAppWidgetId(widgetId)
                }

                widgetId = host.allocateAppWidgetId()
                val bound = widgetManager.bindAppWidgetIdIfAllowed(
                    widgetId,
                    info.profile,
                    info.provider,
                    null,
                )
                if (!bound) {
                    // Evergreen: an allocated id without a provider makes Android 10's
                    // AppWidgetService throw in getHostedWidgetPackages(), which breaks every
                    // accessibility query on the launcher window (TalkBack, uiautomator).
                    // Allocate it again only when the user starts the bind flow.
                    host.deleteAppWidgetId(widgetId)
                    widgetId = -1
                }
            }

            prefs.edit { putInt(prefKey, widgetId) }
        }

        fun getBindIntent(): Intent {
            if (widgetId == -1) {
                widgetId = host.allocateAppWidgetId()
                prefs.edit { putInt(prefKey, widgetId) }
            }
            return createBindIntent()
        }

        private fun createBindIntent() = Intent(AppWidgetManager.ACTION_APPWIDGET_BIND)
            .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId)
            .putExtra(AppWidgetManager.EXTRA_APPWIDGET_PROVIDER, info.provider)
    }

    private class WidgetNotBoundException : RuntimeException()

    companion object {

        val INSTANCE = MainThreadInitializedObject(::HeadlessWidgetsManager)
    }
}
