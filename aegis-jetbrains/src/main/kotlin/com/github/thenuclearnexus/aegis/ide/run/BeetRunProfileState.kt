package com.github.thenuclearnexus.aegis.ide.run

import com.github.thenuclearnexus.aegis.getPythonInterpreterPath
import com.intellij.execution.ExecutionException
import com.intellij.execution.configurations.CommandLineState
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.process.ProcessHandler
import com.intellij.execution.process.ProcessTerminatedListener
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.openapi.project.Project
import java.io.File

class BeetRunProfileState(
    environment: ExecutionEnvironment,
    private val configuration: BeetRunConfiguration
) : CommandLineState(environment) {

    override fun startProcess(): ProcessHandler {
        val project: Project = environment.project
        val pythonPath = getPythonInterpreterPath(project) ?: "python"
        val command = mutableListOf(pythonPath, "-m", "beet")
        if (configuration.watch) {
            command.add("watch")
        } else {
            command.add("build")
        }
        val workDir = File(project.basePath ?: ".")
        try {
            val processBuilder = ProcessBuilder(command).directory(workDir)
            val process = processBuilder.start()
            val handler = OSProcessHandler(process, command.joinToString(" "))
            ProcessTerminatedListener.attach(handler)
            return handler
        } catch (e: Exception) {
            throw ExecutionException("Failed to start beet command: ${e.message}", e)
        }
    }
}