package com.github.thenuclearnexus.aegis.lang

import com.intellij.openapi.fileTypes.LanguageFileType
import com.github.thenuclearnexus.aegis.Icons

object McFunctionFileType : LanguageFileType(McFunctionLanguage) {
    override fun getName(): String = "McFunction"
    override fun getDescription(): String = "McFunction is the file type for Minecraft datapack functions."
    override fun getDefaultExtension(): String = "mcfunction"
    override fun getIcon() = Icons.MC_FUNCTION
}