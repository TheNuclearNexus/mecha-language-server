package com.github.thenuclearnexus.aegis.ide.run

import com.intellij.execution.configurations.ConfigurationType
import com.github.thenuclearnexus.aegis.Icons
import com.intellij.execution.configurations.ConfigurationFactory
import com.intellij.execution.configurations.RunConfigurationOptions
import com.intellij.openapi.project.Project

class BeetBuildConfigurationFactory(type: ConfigurationType) : ConfigurationFactory(type) {
    override fun createTemplateConfiguration(project: Project): BeetRunConfiguration {
        return BeetRunConfiguration(project, this, "Beet Build")
    }
    override fun getName(): String = "Build"
    override fun getIcon() = Icons.BEET
    override fun getId(): String = "BEET_BUILD_CONFIGURATION_FACTORY"
    override fun getOptionsClass() = RunConfigurationOptions::class.java
}

class BeetWatchConfigurationFactory(type: ConfigurationType) : ConfigurationFactory(type) {
    override fun createTemplateConfiguration(project: Project): BeetRunConfiguration {
        return BeetRunConfiguration(project, this, "Beet Watch")
    }
    override fun getName(): String = "Watch"
    override fun getIcon() = Icons.BEET
    override fun getId(): String = "BEET_WATCH_CONFIGURATION_FACTORY"
    override fun getOptionsClass() = RunConfigurationOptions::class.java
}

class BeetConfigurationType : ConfigurationType {
    override fun getDisplayName(): String = "Beet"
    override fun getConfigurationTypeDescription(): String = "Beet is a build tool for Minecraft datapacks."
    override fun getIcon() = Icons.BEET
    override fun getId(): String = "BEET_RUN_CONFIGURATION_TYPE"

    override fun getConfigurationFactories(): Array<ConfigurationFactory> = arrayOf(
        BeetBuildConfigurationFactory(this),
        BeetWatchConfigurationFactory(this)
    )
}

