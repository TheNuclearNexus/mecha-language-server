package com.github.thenuclearnexus.aegis.ide.lsp

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.IconLoader
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.notification.Notifications
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

private fun getPythonInterpreterPath(): String? {
    val sdk = PythonSdkUtil.getAllSdks().firstOrNull() ?: return null
    return sdk.homePath
}

private fun getSitePackagesPath(): String? {
    val sdk = PythonSdkUtil.getAllSdks().firstOrNull() ?: return null
    return PythonSdkUtil.getSitePackagesDirectory(sdk)?.path
}

private fun hasBeetFile(project: Project): Boolean {
    val baseDir = project.baseDir ?: return false
    return baseDir.findChild("beet.json") != null || baseDir.findChild("beet.toml") != null
}

private class AegisLspServerDescriptor(project: Project) : ProjectWideLspServerDescriptor(project, "Aegis LSP Server")  {
    companion object {
        private val logger = Logger.getInstance(AegisLspServerDescriptor::class.java)
    }

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
        val sitePackagesPath = getSitePackagesPath()
            ?: throw IllegalStateException("Python site-packages directory not found. Please install Python packages.")
        logger.info("Python executable path: $pythonExec")
        logger.info("Site-packages path: $sitePackagesPath")
        return GeneralCommandLine(pythonExec, tempFile.absolutePath, "--site", sitePackagesPath)
    }
}

internal class AegisLspServerSupportProvider : LspServerSupportProvider {
    override fun fileOpened(
        project: Project,
        file: VirtualFile,
        serverStarter: LspServerSupportProvider.LspServerStarter
    ) {
        if (file.extension !in FILE_EXTENSIONS) return

        if (!hasBeetFile(project)) {
            val notificationGroup = NotificationGroupManager.getInstance().getNotificationGroup("Aegis LSP")
            val notification = notificationGroup
                .createNotification("Beet File Missing", "beet.json or beet.toml file not found in project root. LSP server was not started.", NotificationType.WARNING)
            Notifications.Bus.notify(notification, project)
            return
        }
        serverStarter.ensureServerStarted(AegisLspServerDescriptor(project))
    }

    private fun getScaledIcon(): Icon {
        val icon = IconLoader.getIcon("/icons/aegis.png", AegisLspServerSupportProvider::class.java)
        val w = icon.iconWidth
        val h = icon.iconHeight
        val img = UIUtil.createImage(w, h, BufferedImage.TYPE_INT_ARGB)
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
