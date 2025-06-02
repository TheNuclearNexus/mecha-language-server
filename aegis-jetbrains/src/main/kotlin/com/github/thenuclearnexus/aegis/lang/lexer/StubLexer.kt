package com.github.thenuclearnexus.aegis.lang.lexer

import com.intellij.lexer.Lexer
import com.intellij.lexer.LexerPosition

/**
 * A minimal stub lexer for use in language stubs that delegate all logic to LSP.
 */
class StubLexer : Lexer() {
    private var buffer: CharSequence = ""
    override fun start(buffer: CharSequence, startOffset: Int, endOffset: Int, initialState: Int) {
        this.buffer = buffer
    }
    override fun getState(): Int = 0
    override fun getTokenType() = null
    override fun getTokenStart(): Int = 0
    override fun getTokenEnd(): Int = 0
    override fun advance() {}
    override fun getCurrentPosition(): LexerPosition = object : LexerPosition {
        override fun getOffset(): Int = 0
        override fun getState(): Int = 0
    }
    override fun restore(position: LexerPosition) {}
    override fun getBufferSequence(): CharSequence = buffer
    override fun getBufferEnd(): Int = buffer.length
}

