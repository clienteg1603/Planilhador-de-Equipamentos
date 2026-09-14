# Planilhador de Equipamentos

Repositório oficial usado pelo sistema de atualização do **Planilhador de Equipamentos**.

## Atualizações

O programa consulta as **Releases** deste repositório e procura o pacote:

`Planilhador_Equipamentos_Update_vX.Y.Z.zip`

junto do arquivo opcional de integridade:

`Planilhador_Equipamentos_Update_vX.Y.Z.zip.sha256`

A publicação das novas versões é automatizada pelo GitHub Actions.

### Regra do projeto

Sempre que uma nova versão do programa for preparada, ela deve ser **publicada no GitHub** e o usuário deve ser **avisado quando a Release estiver disponível para atualização**.

## Importante

O pacote completo de instalação **não deve ser publicado aqui**, pois contém os modelos internos de Excel usados pela empresa.

As Releases públicas devem conter somente o pacote de atualização, que preserva os modelos já instalados, a pasta compartilhada e as configurações locais.
