"""Interactive setup: credentials never need to be sent through chat."""
import asyncio
from getpass import getpass
from telethon import TelegramClient, functions, types, utils
from core import DATA, INVITE, save_settings, settings


async def main():
    print('\nTRILHA · Conectar Telegram\nFeche o servidor antes de configurar.\n')
    cfg = settings()
    api_id = int(input('API ID (my.telegram.org/apps): ').strip())
    api_hash = getpass('API Hash (entrada oculta): ').strip()
    DATA.mkdir(parents=True, exist_ok=True)
    async with TelegramClient(str(DATA / 'telegram'), api_id, api_hash) as client:
        print('\nEntre com seu telefone, código e senha de duas etapas, se solicitada.')
        # __aenter__ already calls start(), including interactive login.
        saved_invite = cfg.get('invite') or INVITE
        link = input('Convite do curso principal [Enter = manter atual ou escolher entre seus canais]: ').strip() or saved_invite
        invite_hash = link.rstrip('/').split('/')[-1].removeprefix('+')
        chat = None
        if '+' in link or '/joinchat/' in link:
            try:
                invitation = await client(functions.messages.CheckChatInviteRequest(invite_hash))
                if isinstance(invitation, types.ChatInviteAlready):
                    chat = invitation.chat
                else:
                    print('Sua conta ainda não participa deste canal. Entre pelo convite no Telegram e execute novamente.')
                    return
            except Exception as exc:
                print(f'Não foi possível consultar o convite ({type(exc).__name__}). Você pode escolher entre seus canais.')
        else:
            try:
                chat = await client.get_entity(link)
            except Exception:
                pass
        if chat is None:
            dialogs = [d async for d in client.iter_dialogs() if d.is_group or d.is_channel]
            for i, d in enumerate(dialogs, 1):
                print(f'{i:3}. {d.title}')
            selection = int(input('Número do canal na lista: ')) - 1
            if not 0 <= selection < len(dialogs):
                raise ValueError('Seleção inválida')
            chat = dialogs[selection].entity
        cfg.update(api_id=api_id, api_hash=api_hash, chat_id=utils.get_peer_id(chat),
                   chat_title=getattr(chat, 'title', 'Meu curso'), invite=link)
        save_settings(cfg)
        print(f'\nConectado a {cfg["chat_title"]}. Agora execute iniciar.bat e clique em Sincronizar.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print('\nConfiguração interrompida.')
    except Exception as exc:
        print(f'\nFalha ({type(exc).__name__}). Confira os dados e execute novamente.')
        raise SystemExit(1)
