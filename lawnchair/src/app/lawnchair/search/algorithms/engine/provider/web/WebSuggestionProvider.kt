package app.lawnchair.search.algorithms.engine.provider.web

import android.content.Context
import android.util.Log
import app.lawnchair.preferences.PreferenceManager
import app.lawnchair.preferences2.PreferenceManager2
import app.lawnchair.search.algorithms.engine.SearchProvider
import app.lawnchair.search.algorithms.engine.SearchResult
import com.patrykmichalik.opto.core.firstBlocking
import kotlin.time.Duration.Companion.milliseconds
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.emitAll
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.timeout

object WebSuggestionProvider : SearchProvider {
    override val id = "web_suggestions"

    override fun search(
        context: Context,
        query: String,
    ): Flow<List<SearchResult>> {
        val prefs = PreferenceManager.getInstance(context)
        val prefs2 = PreferenceManager2.getInstance(context)

        if (query.isBlank() || !prefs.searchResultStartPageSuggestion.get()) {
            return flow { emit(emptyList()) }
        }

        val provider = prefs2.webSuggestionProvider.firstBlocking()
        val timeout = prefs2.maxWebSuggestionDelay.firstBlocking()
        val maxResults = prefs2.maxWebSuggestionResultCount.firstBlocking()

        val webProvider = provider
            .configure(context)

        // Evergreen: debounce. The search job is cancelled on every keystroke, so waiting here
        // means only the query the user paused on hits the network; the timeout still applies to
        // the request itself.
        return flow {
            delay(WEB_SUGGESTION_DEBOUNCE_MS)
            emitAll(webProvider.getSuggestions(query))
        }
            .timeout((WEB_SUGGESTION_DEBOUNCE_MS + timeout).milliseconds)
            .catch {
                if (it is TimeoutCancellationException) {
                    Log.w(TAG, "Web suggestion request timed out")
                    emit(emptyList())
                }
            }
            .map { suggestions ->
                suggestions
                    .take(maxResults)
                    .map { suggestion ->
                        SearchResult.WebSuggestion(suggestion = suggestion, provider = webProvider.id)
                    }
            }
    }

    const val TAG: String = "WebSuggestionProvider"
    private const val WEB_SUGGESTION_DEBOUNCE_MS = 200L
}
