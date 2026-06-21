# Bot Telegram + Sunize PIX + Railway

Bot com:
- Aviso +18 no /start
- Confirmação de maioridade
- Envio de vídeo após confirmar +18
- Texto de venda com botão
- Plano vitalício R$ 17,49
- Oferta de chamada 25 min por +R$ 15,90
- PIX pela API Sunize
- Webhook para liberar acesso quando status vier AUTHORIZED

## Como subir no Railway

1. Crie um bot no @BotFather e pegue o BOT_TOKEN.
2. Crie um projeto no Railway.
3. Envie este ZIP para um repositório GitHub ou suba os arquivos no Railway.
4. Adicione PostgreSQL no projeto Railway.
5. Configure as variáveis do `.env.example` no painel do Railway.
6. Coloque `media/start.jpg` e `media/start.mp4` no projeto antes do deploy.
7. Configure o webhook da Sunize para:

```text
https://SEU-PROJETO.up.railway.app/sunize/webhook
```

## Variáveis obrigatórias

```env
BOT_TOKEN=
ADMIN_ID=
VIP_LINK=
SUNIZE_API_KEY=
SUNIZE_API_SECRET=
DATABASE_URL=
```

## Segurança

Use somente conteúdo adulto legal, com consentimento, autorização de venda e prova de maioridade de todas as pessoas envolvidas.


## Dados da Sunize

Este ZIP está configurado para usar como padrão:

- Nome: Julia Costa
- Email: juliacosta@gmail.com
- CPF: 12345678910

A Sunize pode recusar se o CPF não for válido. No Railway, você pode alterar em:

```env
DEFAULT_CUSTOMER_NAME=Julia Costa
DEFAULT_CUSTOMER_EMAIL=juliacosta@gmail.com
DEFAULT_CUSTOMER_DOCUMENT=12345678910
DEFAULT_CUSTOMER_PHONE=
```

Se `DEFAULT_CUSTOMER_PHONE` ficar vazio, o bot pede o telefone do cliente antes de gerar o Pix. Se preencher, o Pix é gerado direto depois da oferta.

## Atualização aplicada
- Botões com emojis coloridos para combinar melhor com o texto. O Telegram não permite mudar a cor real dos botões inline, apenas texto/emojis.
- Pix agora envia: texto de pagamento, QR Code separado e código copia e cola separado.
- Foto e vídeo do /start foram incluídos na pasta `media/` como `start.jpg` e `start.mp4`.


## Atualização v3
- Botões sem emojis de cor adicionais.
- Mantém envio da vídeo após confirmação +18.
- Mantém Pix em mensagens separadas: texto, QR Code e código copia e cola.
- Confirme no Railway: START_PHOTO_PATH=media/start.jpg e START_VIDEO_PATH=media/start.mp4


## Atualização v5

- Adicionado botão para copiar o Pix copia e cola quando o cliente recebe o pagamento.
- Se o app do Telegram não suportar cópia direta, o botão envia o código Pix novamente separado.
