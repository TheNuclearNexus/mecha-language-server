package com.github.thenuclearnexus.aegis.ide.lsp

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.platform.lsp.api.LspServer
import com.intellij.platform.lsp.api.LspServerSupportProvider
import com.intellij.platform.lsp.api.ProjectWideLspServerDescriptor
import icons.SpellcheckerIcons
import com.github.thenuclearnexus.aegis.ide.lsp.AegisSettingsConfigurable
import com.intellij.platform.lsp.api.lsWidget.LspServerWidgetItem

private val FILE_EXTENSIONS = setOf("mcfunction", "bolt")

private class AegisLspServerDescriptor(project: Project) : ProjectWideLspServerDescriptor(project, "Aegis LSP Server")  {
    override fun isSupportedFile(file: VirtualFile) = file.extension in FILE_EXTENSIONS
    override fun createCommandLine() = GeneralCommandLine("aegis-lsp-server")
}

internal class AegisLspServerSupportProvider : LspServerSupportProvider {
    override fun fileOpened(
        project: Project,
        file: VirtualFile,
        serverStarter: LspServerSupportProvider.LspServerStarter
    ) {
        if (file.extension in FILE_EXTENSIONS) {
            serverStarter.ensureServerStarted(AegisLspServerDescriptor(project))
        }
    }
    override fun createLspServerWidgetItem(lspServer: LspServer, currentFile: VirtualFile?) = LspServerWidgetItem(
        lspServer,
        currentFile,
        SpellcheckerIcons.Spellcheck,
        settingsPageClass = AegisSettingsConfigurable::class.java
    )
}
