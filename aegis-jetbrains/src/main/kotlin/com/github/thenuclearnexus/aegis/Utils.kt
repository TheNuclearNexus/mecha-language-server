package com.github.thenuclearnexus.aegis

import com.intellij.openapi.util.IconLoader
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