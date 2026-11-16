package com.paradoxplaza.prisonarchitect.patools

import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Process
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory

class NativeModsActivity : ComponentActivity() {
    private lateinit var model: NativeModsModel
    private val picker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        model.onArchivePicked(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        model = ViewModelProvider.create(this, viewModelFactory {
            initializer { NativeModsModel(applicationContext) }
        })[NativeModsModel::class]
        if (savedInstanceState != null && !model.pickingArchive) {
            model.restorePicker(savedInstanceState)
        }
        if (savedInstanceState == null) {
            receiveExternalArchive(intent)
        } else if (model.externalArchive == null) {
            savedInstanceState.getString("externalArchive")?.let { offerExternalArchive(Uri.parse(it)) }
        }
        setContent {
            NativeModsRoute(
                model = model,
                pickMod = ::pickMod,
                openGame = ::openGame,
            )
        }
    }

    override fun onResume() {
        super.onResume()
        model.onResume()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        receiveExternalArchive(intent)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        if (model.pickingArchive) {
            outState.putBoolean("pickingArchive", true)
        }
        model.externalArchive?.let { outState.putString("externalArchive", it.toString()) }
    }

    private fun receiveExternalArchive(intent: Intent) {
        if (intent.action == Intent.ACTION_VIEW) offerExternalArchive(intent.data)
    }

    private fun offerExternalArchive(uri: Uri?) {
        if (uri?.scheme != "content" || uri.authority.isNullOrEmpty()) {
            model.error(R.string.mods_import_unreadable)
            return
        }
        if (checkUriPermission(uri, Process.myPid(), Process.myUid(), Intent.FLAG_GRANT_READ_URI_PERMISSION)
            != PackageManager.PERMISSION_GRANTED
        ) {
            model.error(R.string.mods_import_unreadable)
            return
        }
        model.offerExternalArchive(uri)
    }

    private fun pickMod() {
        model.startPicker()
        try {
            picker.launch(arrayOf("*/*"))
        } catch (_: ActivityNotFoundException) {
            model.onArchivePicked(null)
            model.error(R.string.mods_picker_unavailable)
        }
    }

    private fun openGame() {
        val intent = Intent(Intent.ACTION_MAIN)
            .setClassName(packageName, "com.paradoxplaza.prisonarchitect.core.MainActivity")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            model.error(R.string.mods_game_unavailable)
        }
    }
}
