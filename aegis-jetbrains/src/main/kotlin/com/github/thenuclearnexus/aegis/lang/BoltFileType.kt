package com.github.thenuclearnexus.aegis.lang

import com.intellij.openapi.fileTypes.LanguageFileType
import com.intellij.icons.AllIcons

object BoltFileType : LanguageFileType(BoltLanguage) {
    override fun getName(): String = "Bolt"
    override fun getDescription(): String = "Bolt is the file type for high-level Minecraft datapack functions, adding support for python-like syntax and features in addition to the standard McFunction syntax."
    override fun getDefaultExtension(): String = "bolt"
    override fun getIcon() = AllIcons.FileTypes.Text
}
