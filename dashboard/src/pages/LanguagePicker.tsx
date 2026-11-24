// SPDX-License-Identifier: Apache-2.0
// Settings > Appearance > Language. Saved for this person only; it changes nothing on the box, so
// it needs no approval.
import { Card } from '@onemind/ui';
import { localeStore } from '../i18n/localeStore';
import { availableLocales, getLocale, setLocale, t, useLocale } from '../i18n';
import { useSignedIn } from '../session';

export function LanguagePicker() {
  const { person } = useSignedIn();
  const locale = useLocale();
  const options = availableLocales();
  const choose = (id: string) => {
    localeStore(person).save(id);
    setLocale(id);
  };
  return (
    <Card title={t('language.title')} level={2}>
      <p className="om-hint">{t('language.lede')}</p>
      <label htmlFor="ui-language">{t('language.label')}</label>{' '}
      <select id="ui-language" value={locale} onChange={(e) => choose(e.target.value)}>
        {options.map((o) => (
          <option key={o.id} value={o.id} lang={o.id}>
            {o.label}
          </option>
        ))}
      </select>
      {options.length === 1 && <p className="om-hint">{t('language.only', { name: options[0]!.label })}</p>}
      <p className="om-hint">{t('language.current', { id: getLocale() })}</p>
    </Card>
  );
}
