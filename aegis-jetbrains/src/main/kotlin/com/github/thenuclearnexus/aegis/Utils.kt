package com.github.thenuclearnexus.aegis

import com.intellij.openapi.project.Project
import com.intellij.openapi.util.IconLoader
import com.intellij.openapi.vfs.VirtualFileManager
import com.jetbrains.python.sdk.pythonSdk
import java.awt.GraphicsEnvironment
import java.awt.Transparency
import java.awt.image.BufferedImage
import javax.swing.Icon
import javax.swing.ImageIcon


fun getIcon(path: String, width: Int, height: Int, aClass: Class<*>): Icon {
    val icon = IconLoader.getIcon(path, aClass)
    val w = icon.iconWidth
    val h = icon.iconHeight
    val config = GraphicsEnvironment.getLocalGraphicsEnvironment().defaultScreenDevice.defaultConfiguration
    val img: BufferedImage = config.createCompatibleImage(w, h, Transparency.TRANSLUCENT)
    val g = img.createGraphics()
    icon.paintIcon(null, g, 0, 0)
    g.dispose()
    val scaled = img.getScaledInstance(width, height, BufferedImage.SCALE_SMOOTH)
    return ImageIcon(scaled)
}

fun hasBeetFile(project: Project): Boolean {
    val basePath = project.basePath ?: return false
    val baseDir = VirtualFileManager.getInstance().findFileByUrl("file://$basePath") ?: return false
    return baseDir.findChild("beet.json") != null || baseDir.findChild("beet.yml") != null
            || baseDir.findChild("beet.yaml") != null
}

fun getPythonInterpreterPath(project: Project): String? {
    val sdk = project.pythonSdk ?: return null
    return sdk.homePath
}