package com.github.thenuclearnexus.aegis.ide.run

import com.intellij.execution.Executor
import com.intellij.execution.configurations.*
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.openapi.options.SettingsEditor
import com.intellij.openapi.project.Project

class BeetRunConfiguration(project: Project, factory: ConfigurationFactory, name: String)
    : LocatableConfigurationBase<BeetRunConfigurationOptions>(project, factory, name) {

    override fun getOptionsClass(): Class<out BeetRunConfigurationOptions> {
        return BeetRunConfigurationOptions::class.java
    }

    var watch: Boolean
        get() = (options as BeetRunConfigurationOptions).watch
        set(value) {
            (options as BeetRunConfigurationOptions).watch = value
        }

    override fun getConfigurationEditor(): SettingsEditor<out RunConfiguration> {
        return BeetSettingsEditor()
    }

    override fun getState(executor: Executor, environment: ExecutionEnvironment): RunProfileState? {
        return BeetRunProfileState(environment, this)
    }
}