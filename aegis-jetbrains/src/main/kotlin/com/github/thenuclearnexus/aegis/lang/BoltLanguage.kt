package com.github.thenuclearnexus.aegis.lang

import com.intellij.lang.Language

object BoltLanguage : Language("Bolt") {
    private fun readResolve(): Any = BoltLanguage
    override fun getDisplayName(): String = "Bolt"
    override fun getID(): String = "bolt"
    override fun getAssociatedFileType() = BoltFileType
}