package com.github.thenuclearnexus.aegis.ide.lsp

import com.intellij.openapi.options.Configurable
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.JLabel

class AegisSettingsConfigurable : Configurable {
    private var settingsPanel: JPanel? = null

    override fun getDisplayName(): String = "Aegis LSP Settings"

    override fun createComponent(): JComponent? {
        if (settingsPanel == null) {
            settingsPanel = JPanel().apply {
                add(JLabel("Aegis LSP settings can be configured here."))
            }
        }
        return settingsPanel
    }

    override fun isModified(): Boolean = false

    override fun apply() {}

    override fun reset() {}

    override fun disposeUIResources() {
        settingsPanel = null
    }
}

