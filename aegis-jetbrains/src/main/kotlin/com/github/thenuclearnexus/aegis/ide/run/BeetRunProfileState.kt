package com.github.thenuclearnexus.aegis.ide.run

import com.intellij.execution.ExecutionResult
import com.intellij.execution.Executor
import com.intellij.execution.configurations.CommandLineState
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.process.ProcessTerminatedListener
import com.intellij.execution.runners.ExecutionEnvironment

class BeetRunProfileState(environment: ExecutionEnvironment, private val configuration: BeetRunConfiguration)
    : CommandLineState(environment) {

    override fun startProcess(): OSProcessHandler {
        val projectPath = configuration.project.basePath ?: ""

        val command = if (configuration.watch) "watch" else "build"

        val commandLine = GeneralCommandLine("beet", command)
            .withWorkDirectory(projectPath)
            .withRedirectErrorStream(true)

        val processHandler = OSProcessHandler(commandLine)
        ProcessTerminatedListener.attach(processHandler)
        return processHandler
    }

    override fun execute(executor: Executor, runner: com.intellij.execution.runners.ProgramRunner<*>): ExecutionResult {
        val processHandler = startProcess()
        val console = createConsole(executor)
        return com.intellij.execution.DefaultExecutionResult(console, processHandler)
    }
}

