package com.github.thenuclearnexus.aegis.lang

import com.intellij.lang.Language

object McFunctionLanguage : Language("McFunction") {
    private fun readResolve(): Any = McFunctionLanguage
    override fun getDisplayName(): String = "McFunction"
    override fun getID(): String = "mcfunction"
    override fun getAssociatedFileType() = McFunctionFileType
}