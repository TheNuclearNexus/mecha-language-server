package com.github.thenuclearnexus.aegis.actions

import com.github.thenuclearnexus.aegis.Icons
import com.intellij.ide.actions.CreateFileFromTemplateAction
import com.intellij.ide.actions.CreateFileFromTemplateDialog
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDirectory
import com.intellij.psi.PsiFile

class NewBoltFileAction : CreateFileFromTemplateAction(
    "Bolt File",
    "Create a new Bolt file",
    Icons.BOLT
) {
    override fun buildDialog(project: Project, directory: PsiDirectory, builder: CreateFileFromTemplateDialog.Builder) {
        builder.setTitle("New Bolt File")
            .addKind("Bolt File", Icons.BOLT, "Bolt File.bolt")
    }

    override fun getActionName(directory: PsiDirectory, newName: String, templateName: String): String {
        return "Create Bolt File"
    }

    override fun createFile(name: String?, templateName: String?, dir: PsiDirectory): PsiFile? {
        return super.createFile(name, templateName, dir)
    }
}
