package com.github.thenuclearnexus.aegis.ide.run

import com.intellij.execution.Executor
import com.intellij.execution.configurations.*
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.openapi.options.SettingsEditor
import com.intellij.openapi.project.Project

class BeetRunConfiguration(
    project: Project,
    factory: ConfigurationFactory,
    name: String
) : RunConfigurationBase<RunConfigurationOptions>(project, factory, name) {

    override fun getOptions(): RunConfigurationOptions = super.getOptions()

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

    fun isWatch(): Boolean = "Watch" in factory?.name.toString()
}

