"""Save private course invitations in the ignored local database."""
import re
from core import db, settings, save_settings


def main():
    with db() as con:
        courses = [dict(row) for row in con.execute('SELECT * FROM courses ORDER BY rowid')]
    print('\nTRILHA · Convites privados dos cursos\nEnter mantém a configuração atual.\n')
    for course in courses:
        link = input(f"Convite para {course['name']}: ").strip()
        if not link:
            continue
        if not re.fullmatch(r'https://t\.me/(?:\+|joinchat/)[A-Za-z0-9_-]+/?',link):
            print('Formato de convite inválido. Use o link privado https://t.me/+...')
            continue
        with db() as con:
            con.execute('UPDATE courses SET invite=? WHERE id=?',(link,course['id']))
        cfg = settings()
        key = {'autodidata': 'invite', 'wise-up': 'wise_invite', 'vibe-coding': 'vibe_invite'}.get(course['id'])
        if key:
            cfg[key] = link
        save_settings(cfg)
        print('Convite salvo localmente.')
    print('\nAgora abra a plataforma, escolha o curso e sincronize.')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt,EOFError):
        print('\nConfiguração interrompida.')
