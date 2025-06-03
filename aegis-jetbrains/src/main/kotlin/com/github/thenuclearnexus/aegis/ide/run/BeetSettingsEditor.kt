package com.github.thenuclearnexus.aegis.ide.run

import com.intellij.openapi.options.SettingsEditor
import com.intellij.ui.components.JBCheckBox
import com.intellij.util.ui.FormBuilder
import javax.swing.JComponent
import javax.swing.JPanel

class BeetSettingsEditor : SettingsEditor<BeetRunConfiguration>() {
    private val panel: JPanel
    private val watchCheckBox: JBCheckBox = JBCheckBox("Watch (run 'beet watch' instead of 'beet build')")

    init {
        panel = FormBuilder.createFormBuilder()
            .addComponent(watchCheckBox)
            .panel
    }

    override fun resetEditorFrom(configuration: BeetRunConfiguration) {
        watchCheckBox.isSelected = configuration.watch
    }

    override fun applyEditorTo(configuration: BeetRunConfiguration) {
        configuration.watch = watchCheckBox.isSelected
    }

    override fun createEditor(): JComponent {
        return panel
    }
}

