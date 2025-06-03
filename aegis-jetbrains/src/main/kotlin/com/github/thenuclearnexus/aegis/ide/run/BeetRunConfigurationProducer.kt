package com.github.thenuclearnexus.aegis.ide.run

import com.intellij.execution.actions.ConfigurationContext
import com.intellij.execution.actions.LazyRunConfigurationProducer
import com.intellij.execution.configurations.ConfigurationFactory
import com.intellij.openapi.util.Ref
import com.intellij.psi.PsiElement
import com.github.thenuclearnexus.aegis.hasBeetFile

class BeetRunConfigurationProducer : LazyRunConfigurationProducer<BeetRunConfiguration>() {
    override fun getConfigurationFactory(): ConfigurationFactory {
        return BeetConfigurationType().configurationFactories[0]
    }

    override fun setupConfigurationFromContext(
        configuration: BeetRunConfiguration,
        context: ConfigurationContext,
        sourceElement: Ref<PsiElement>
    ): Boolean {
        if (hasBeetFile(context.project)) {
            configuration.name = "Beet Build"
            configuration.watch = false
            sourceElement.set(context.psiLocation)
            return true
        }
        return false
    }

    override fun isConfigurationFromContext(
        configuration: BeetRunConfiguration,
        context: ConfigurationContext
    ): Boolean {
        return hasBeetFile(context.project) && configuration.type is BeetConfigurationType
    }
}

