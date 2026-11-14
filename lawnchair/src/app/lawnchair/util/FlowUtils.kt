package app.lawnchair.util

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import androidx.compose.runtime.Composable
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.buffer
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.runBlocking

fun <T> Flow<T>.firstBlocking() = runBlocking { first() }

@Composable
fun <T> Flow<T>.collectAsStateBlocking() = collectAsStateWithLifecycle(initialValue = firstBlocking())

fun broadcastReceiverFlow(context: Context, filter: IntentFilter) = callbackFlow {
    val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            trySend(intent)
        }
    }
    context.registerReceiver(receiver, filter)
    awaitClose { context.unregisterReceiver(receiver) }
}

fun <T> Flow<T>.dropWhileBusy(): Flow<T> = channelFlow {
    collect { trySend(it) }
}.buffer(0)

fun <T> Flow<T>.subscribeBlocking(
    scope: CoroutineScope,
    block: (T) -> Unit,
) {
    // Evergreen: the callback used to run twice on subscription (once here, then for the first
    // emission, because onEach came before drop(1)), and distinctUntilChanged() came after the
    // callback, so it filtered nothing.
    var last = firstBlocking()
    block(last)
    this
        .onEach {
            if (it != last) {
                last = it
                block(it)
            }
        }
        .launchIn(scope = scope)
}
