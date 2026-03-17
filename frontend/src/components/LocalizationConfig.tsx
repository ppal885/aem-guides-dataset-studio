import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Button } from './ui/button';
import { X, Plus } from 'lucide-react';

interface LocalizationConfigProps {
  recipe: {
    base_recipe?: any;
    source_language?: string;
    target_languages?: string[];
    include_translation_metadata?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function LocalizationConfig({ recipe, onChange }: LocalizationConfigProps) {
  const addTargetLanguage = () => {
    const languages = recipe.target_languages || [];
    onChange({ ...recipe, target_languages: [...languages, ''] });
  };

  const updateTargetLanguage = (index: number, value: string) => {
    const languages = [...(recipe.target_languages || [])];
    languages[index] = value;
    onChange({ ...recipe, target_languages: languages });
  };

  const removeTargetLanguage = (index: number) => {
    const languages = [...(recipe.target_languages || [])];
    languages.splice(index, 1);
    onChange({ ...recipe, target_languages: languages });
  };

  return (
    <div className="space-y-4">
      <div>
        <Label>Source Language</Label>
        <Input
          value={recipe.source_language || 'en'}
          onChange={(e) => onChange({ ...recipe, source_language: e.target.value })}
          placeholder="e.g., en"
        />
        <p className="text-sm text-gray-500 mt-1">
          Language code for source content (ISO 639-1)
        </p>
      </div>

      <div>
        <Label>Target Languages</Label>
        <div className="space-y-2">
          {(recipe.target_languages || ['es', 'fr', 'de']).map((lang, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={lang}
                onChange={(e) => updateTargetLanguage(index, e.target.value)}
                placeholder="e.g., es, fr, de"
              />
              <Button
                onClick={() => removeTargetLanguage(index)}
                variant="ghost"
                size="sm"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button onClick={addTargetLanguage} variant="outline" size="sm">
            <Plus className="h-4 w-4 mr-2" />
            Add Target Language
          </Button>
        </div>
        <p className="text-sm text-gray-500 mt-1">
          Languages to generate variants for
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="translation-metadata"
          checked={recipe.include_translation_metadata !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, include_translation_metadata: checked })}
        />
        <Label htmlFor="translation-metadata">Include Translation Metadata</Label>
      </div>

      <div className="border rounded p-4 bg-gray-50">
        <Label className="text-sm font-semibold">Base Recipe</Label>
        <p className="text-sm text-gray-600 mt-1">
          Select a base recipe to localize. The localization will generate language variants
          of all content in the base recipe.
        </p>
        <p className="text-xs text-gray-500 mt-2">
          Base recipe configuration will be set when you select a recipe type.
        </p>
      </div>
    </div>
  );
}
