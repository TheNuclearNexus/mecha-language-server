package com.github.thenuclearnexus.aegis.ide.lsp

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.IconLoader
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.platform.lsp.api.LspServer
import com.intellij.platform.lsp.api.LspServerSupportProvider
import com.intellij.platform.lsp.api.ProjectWideLspServerDescriptor
import com.intellij.platform.lsp.api.lsWidget.LspServerWidgetItem
import com.intellij.util.ui.UIUtil
import kotlin.io.path.createTempFile
import com.jetbrains.python.sdk.PythonSdkUtil
import java.awt.Image
import java.awt.image.BufferedImage
import javax.swing.Icon
import javax.swing.ImageIcon

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
            ?: throw IllegalStateException("Resource \$resourceName not found in plugin JAR.")
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

    private fun getScaledIcon(): Icon {
        val icon = IconLoader.getIcon("/icons/aegis.png", AegisLspServerSupportProvider::class.java)
        val w = icon.iconWidth
        val h = icon.iconHeight
        val img = UIUtil.createImage(w, h, java.awt.image.BufferedImage.TYPE_INT_ARGB)
        val g = img.createGraphics()
        icon.paintIcon(null, g, 0, 0)
        g.dispose()
        val scaled = img.getScaledInstance(16, 16, Image.SCALE_SMOOTH)
        return ImageIcon(scaled)
    }
    override fun createLspServerWidgetItem(lspServer: LspServer, currentFile: VirtualFile?) =
        LspServerWidgetItem(
            lspServer,
            currentFile,
            getScaledIcon(),
            settingsPageClass = AegisSettingsConfigurable::class.java
        )
}
