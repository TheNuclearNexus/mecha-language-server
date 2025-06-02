package com.github.thenuclearnexus.aegis.lang.parser

import com.github.thenuclearnexus.aegis.lang.McFunctionLanguage
import com.github.thenuclearnexus.aegis.lang.McFunctionFileType
import com.github.thenuclearnexus.aegis.lang.lexer.StubLexer
import com.intellij.lang.ASTNode
import com.intellij.lang.ParserDefinition
import com.intellij.lang.PsiParser
import com.intellij.lexer.Lexer
import com.intellij.openapi.fileTypes.FileType
import com.intellij.openapi.project.Project
import com.intellij.psi.FileViewProvider
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiElementVisitor
import com.intellij.psi.PsiFile
import com.intellij.psi.impl.source.PsiFileImpl
import com.intellij.psi.tree.IFileElementType
import com.intellij.psi.tree.TokenSet

class McFunctionParserDefinition : ParserDefinition {
    override fun createLexer(project: Project): Lexer = StubLexer()

    override fun createParser(project: Project): PsiParser = PsiParser { _, _ -> throw UnsupportedOperationException("McFunctionParserDefinition does not support parsing") }
    override fun getFileNodeType(): IFileElementType = IFileElementType(McFunctionLanguage)
    override fun getCommentTokens(): TokenSet = TokenSet.EMPTY
    override fun getStringLiteralElements(): TokenSet = TokenSet.EMPTY
    override fun createElement(node: ASTNode): PsiElement = node.psi
    override fun createFile(viewProvider: FileViewProvider): PsiFile = object : PsiFileImpl(IFileElementType(McFunctionLanguage), IFileElementType(McFunctionLanguage), viewProvider) {
        override fun getFileType(): FileType = McFunctionFileType
        override fun accept(visitor: PsiElementVisitor) { visitor.visitFile(this) }
    }
}