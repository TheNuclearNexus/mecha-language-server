package com.github.thenuclearnexus.aegis.ide.run

import com.intellij.execution.configurations.LocatableRunConfigurationOptions
import com.intellij.openapi.components.StoredProperty

class BeetRunConfigurationOptions : LocatableRunConfigurationOptions() {
    private val _watch: StoredProperty<Boolean> = this.property(false)
    var watch: Boolean
        get() = _watch.getValue(this)
        set(value) = _watch.setValue(this, value)
}

