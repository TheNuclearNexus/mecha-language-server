package com.github.thenuclearnexus.aegis.ide.run

import com.github.thenuclearnexus.aegis.hasBeetFile
import com.intellij.execution.RunManager
import com.intellij.openapi.project.Project

fun addBeetRunConfigurationsIfNeeded(project: Project) {
    if (!hasBeetFile(project)) return
    val runManager = RunManager.getInstance(project)
    val existingNames = runManager.allConfigurationsList.map { it.name }

    val beetType = BeetConfigurationType()
    val buildFactory = BeetBuildConfigurationFactory(beetType)
    val watchFactory = BeetWatchConfigurationFactory(beetType)

    if ("Beet Build" !in existingNames) {
        val buildSettings = runManager.createConfiguration("Beet Build", buildFactory)
        runManager.addConfiguration(buildSettings)
    }
    if ("Beet Watch" !in existingNames) {
        val watchSettings = runManager.createConfiguration("Beet Watch", watchFactory)
        runManager.addConfiguration(watchSettings)
    }
}

