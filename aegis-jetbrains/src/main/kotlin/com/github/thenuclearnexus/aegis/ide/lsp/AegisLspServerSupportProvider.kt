package com.github.thenuclearnexus.aegis.ide.lsp

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.platform.lsp.api.LspServer
import com.intellij.platform.lsp.api.LspServerSupportProvider
import com.intellij.platform.lsp.api.ProjectWideLspServerDescriptor
import icons.SpellcheckerIcons
import com.intellij.platform.lsp.api.lsWidget.LspServerWidgetItem
import kotlin.io.path.createTempFile
import com.jetbrains.python.sdk.PythonSdkUtil

private val FILE_EXTENSIONS = setOf("mcfunction", "bolt")

fun getPythonInterpreterPath(): String? {
    val sdk = PythonSdkUtil.getAllSdks().firstOrNull() ?: return null
    return sdk.homePath
}

private class AegisLspServerDescriptor(project: Project) : ProjectWideLspServerDescriptor(project, "Aegis LSP Server")  {
    override fun isSupportedFile(file: VirtualFile) = file.extension in FILE_EXTENSIONS
    override fun createCommandLine(): GeneralCommandLine {
        val resourceName = "/language_server.pyz"
        val inputStream = javaClass.getResourceAsStream(resourceName)
            ?: throw IllegalStateException("Resource $resourceName not found in plugin JAR.")
        val tempFile = createTempFile("language_server", ".pyz").toFile()
        tempFile.deleteOnExit()
        inputStream.use { input ->
            tempFile.outputStream().use { output ->
                input.copyTo(output)
            }
        }
        val pythonExec = getPythonInterpreterPath()
            ?: throw IllegalStateException("Python interpreter not found. Please install Python.")
        return GeneralCommandLine(pythonExec, tempFile.absolutePath)
    }
}

internal class AegisLspServerSupportProvider : LspServerSupportProvider {
    override fun fileOpened(
        project: Project,
        file: VirtualFile,
        serverStarter: LspServerSupportProvider.LspServerStarter
    ) {
        if (file.extension in FILE_EXTENSIONS) {
            serverStarter.ensureServerStarted(AegisLspServerDescriptor(project))
        }
    }
    override fun createLspServerWidgetItem(lspServer: LspServer, currentFile: VirtualFile?) = LspServerWidgetItem(
        lspServer,
        currentFile,
        SpellcheckerIcons.Spellcheck,
        settingsPageClass = AegisSettingsConfigurable::class.java
    )
}
