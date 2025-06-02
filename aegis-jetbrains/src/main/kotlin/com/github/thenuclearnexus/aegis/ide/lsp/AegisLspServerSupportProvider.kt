package com.github.thenuclearnexus.aegis.ide.lsp

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.notification.Notifications
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.IconLoader
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.platform.lsp.api.LspServer
import com.intellij.platform.lsp.api.LspServerSupportProvider
import com.intellij.platform.lsp.api.ProjectWideLspServerDescriptor
import com.intellij.platform.lsp.api.lsWidget.LspServerWidgetItem
import com.jetbrains.python.sdk.PythonSdkUtil
import java.awt.GraphicsEnvironment
import java.awt.Transparency
import java.awt.image.BufferedImage
import javax.swing.Icon
import javax.swing.ImageIcon
import kotlin.io.path.createTempFile

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
    val basePath = project.basePath ?: return false
    val baseDir = VirtualFileManager.getInstance().findFileByUrl("file://$basePath") ?: return false
    return baseDir.findChild("beet.json") != null || baseDir.findChild("beet.toml") != null
}

private class AegisLspServerDescriptor(project: Project) :
    ProjectWideLspServerDescriptor(project, "Aegis LSP Server") {
    companion object {
        private val logger = Logger.getInstance(AegisLspServerDescriptor::class.java)
    }

    override fun isSupportedFile(file: VirtualFile) = file.extension in FILE_EXTENSIONS

    override fun createCommandLine(): GeneralCommandLine {
        val resourceName = "/language_server.pyz"
        val inputStream = javaClass.getResourceAsStream(resourceName)
            ?: run {
                val notificationGroup = NotificationGroupManager.getInstance().getNotificationGroup("Aegis LSP")
                val notification = notificationGroup.createNotification(
                    "Resource missing",
                    "Resource $resourceName not found in plugin JAR.",
                    NotificationType.ERROR
                )
                Notifications.Bus.notify(notification, project)
                return GeneralCommandLine("echo", "Resource missing")
            }
        val tempFile = createTempFile("language_server", ".pyz").toFile()
        tempFile.deleteOnExit()
        inputStream.use { input ->
            tempFile.outputStream().use { output ->
                input.copyTo(output)
            }
        }
        val pythonExec = getPythonInterpreterPath()
        if (pythonExec == null) {
            val notificationGroup = NotificationGroupManager.getInstance().getNotificationGroup("Aegis LSP")
            val notification = notificationGroup.createNotification(
                "Python interpreter missing",
                "The Python interpreter was not found. Please setup the Python SDK.",
                NotificationType.ERROR
            )
            Notifications.Bus.notify(notification, project)
            return GeneralCommandLine("echo", "Python interpreter missing")
        }
        val sitePackagesPath = getSitePackagesPath()
        if (sitePackagesPath == null) {
            val notificationGroup = NotificationGroupManager.getInstance().getNotificationGroup("Aegis LSP")
            val notification = notificationGroup.createNotification(
                "Site-packages missing",
                "The Python site-packages directory was not found. Please fix Python SDK.",
                NotificationType.WARNING
            )
            Notifications.Bus.notify(notification, project)
        }
        logger.info("Python executable path: $pythonExec")
        logger.info("Site-packages path: $sitePackagesPath")
        if (sitePackagesPath == null) {
            return GeneralCommandLine(pythonExec, tempFile.absolutePath)
        }
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
            val notification = notificationGroup.createNotification(
                "Beet config missing",
                "The file beet.json or beet.toml was not found in project root. LSP server was not started. Please add the file.",
                NotificationType.WARNING
            )
            Notifications.Bus.notify(notification, project)
            return
        }
        serverStarter.ensureServerStarted(AegisLspServerDescriptor(project))
    }

    private fun getScaledIcon(): Icon {
        val icon = IconLoader.getIcon("/icons/aegis.png", AegisLspServerSupportProvider::class.java)
        val w = icon.iconWidth
        val h = icon.iconHeight
        val config = GraphicsEnvironment.getLocalGraphicsEnvironment().defaultScreenDevice.defaultConfiguration
        val img: BufferedImage = config.createCompatibleImage(w, h, Transparency.TRANSLUCENT)
        val g = img.createGraphics()
        icon.paintIcon(null, g, 0, 0)
        g.dispose()
        val scaled = img.getScaledInstance(16, 16, BufferedImage.SCALE_SMOOTH)
        return ImageIcon(scaled)
    }

    override fun createLspServerWidgetItem(lspServer: LspServer, currentFile: VirtualFile?) =
        LspServerWidgetItem(
            lspServer,
            currentFile,
            getScaledIcon()
        )
}
