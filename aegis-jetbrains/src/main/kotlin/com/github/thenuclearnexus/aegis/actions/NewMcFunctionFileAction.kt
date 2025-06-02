package com.github.thenuclearnexus.aegis.actions

import com.intellij.ide.actions.CreateFileFromTemplateAction
import com.intellij.ide.actions.CreateFileFromTemplateDialog
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.NlsContexts
import com.intellij.psi.PsiDirectory
import com.intellij.psi.PsiFile
import org.jetbrains.annotations.NonNls

class NewMcFunctionFileAction : CreateFileFromTemplateAction(
    "mcfunction File",
    "Create a new mcfunction file",
    null
) {
    override fun buildDialog(project: Project, directory: PsiDirectory, builder: CreateFileFromTemplateDialog.Builder) {
        builder.setTitle("New mcfunction File")
            .addKind("mcfunction File", null, "McFunction File.mcfunction")
    }

    override fun getActionName(directory: PsiDirectory, newName: String, templateName: String): String {
        return "Create McFunction File"
    }

    override fun createFile(name: String?, templateName: String?, dir: PsiDirectory): PsiFile? {
        return super.createFile(name, templateName, dir)
    }
}

