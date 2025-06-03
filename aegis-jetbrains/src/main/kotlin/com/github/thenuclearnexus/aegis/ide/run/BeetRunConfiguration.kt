package com.github.thenuclearnexus.aegis.ide.run

import com.intellij.execution.Executor
import com.intellij.execution.configurations.*
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.openapi.options.SettingsEditor
import com.intellij.openapi.project.Project

class BeetRunConfiguration(project: Project, factory: ConfigurationFactory, name: String)
    : LocatableConfigurationBase<LocatableRunConfigurationOptions>(project, factory, name) {

    override fun getConfigurationEditor(): SettingsEditor<out RunConfiguration> {
        return object : SettingsEditor<RunConfiguration>() {
            override fun resetEditorFrom(s: RunConfiguration) {}
            override fun applyEditorTo(s: RunConfiguration) {}
            override fun createEditor() = javax.swing.JPanel()
        }
    }

    override fun getState(executor: Executor, environment: ExecutionEnvironment): RunProfileState? {
        return BeetRunProfileState(environment, this)
    }

    override fun suggestedName(): String {
        val currentName = super.getName()
        return if (currentName == "Untitled") {
            when (factory?.id) {
                "BEET_WATCH_CONFIGURATION_FACTORY" -> "Beet Watch"
                else -> "Beet Build"
            }
        } else {
            currentName
        }
    }

    fun isWatch(): Boolean = factory?.id == "BEET_WATCH_CONFIGURATION_FACTORY"
}

