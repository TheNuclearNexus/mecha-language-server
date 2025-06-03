package com.github.thenuclearnexus.aegis.ide.run

import com.github.thenuclearnexus.aegis.hasBeetFile
import com.intellij.execution.RunManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.diagnostic.Logger

fun addBeetRunConfigurationsIfNeeded(project: Project) {
    val logger = Logger.getInstance("BeetRunConfigurationUtil")
    if (!hasBeetFile(project)) {
        logger.info("No beet file found in project: ${project.name}")
        return
    }
    val runManager = RunManager.getInstance(project)
    val existingNames = runManager.allConfigurationsList.map { it.name }

    val beetType = BeetConfigurationType()
    val buildFactory = BeetBuildConfigurationFactory(beetType)
    val watchFactory = BeetWatchConfigurationFactory(beetType)

    if ("Beet Build" !in existingNames) {
        val buildSettings = runManager.createConfiguration("Beet Build", buildFactory)
        runManager.addConfiguration(buildSettings)
        logger.info("Added Beet Build run configuration to project: ${project.name}")
    } else {
        logger.info("Beet Build run configuration already exists in project: ${project.name}")
    }
    if ("Beet Watch" !in existingNames) {
        val watchSettings = runManager.createConfiguration("Beet Watch", watchFactory)
        runManager.addConfiguration(watchSettings)
        logger.info("Added Beet Watch run configuration to project: ${project.name}")
    } else {
        logger.info("Beet Watch run configuration already exists in project: ${project.name}")
    }
}

