import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

interface KeywordMetadataConfigProps {
  recipe: any;
  onChange: (recipe: any) => void;
}

export function KeywordMetadataConfig({ recipe, onChange }: KeywordMetadataConfigProps) {
  const handleChange = (field: string, value: any) => {
    onChange({
      ...recipe,
      [field]: value,
    });
  };

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="id_prefix">ID Prefix</Label>
        <Input
          id="id_prefix"
          type="text"
          value={recipe.id_prefix || 't'}
          onChange={(e) => handleChange('id_prefix', e.target.value)}
          placeholder="t"
          className="mt-1"
        />
        <p className="text-sm text-gray-500 mt-1">
          Prefix for generated IDs (must start with letter or underscore)
        </p>
      </div>

      <div>
        <Label htmlFor="num_keywords">Number of Keywords</Label>
        <Input
          id="num_keywords"
          type="number"
          min="1"
          max="50"
          value={recipe.num_keywords || 10}
          onChange={(e) => handleChange('num_keywords', parseInt(e.target.value) || 10)}
          className="mt-1"
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of keyword metadata keys to generate (1-50)
        </p>
      </div>

      <div>
        <Label htmlFor="num_categories">Number of Categories</Label>
        <Input
          id="num_categories"
          type="number"
          min="1"
          max="20"
          value={recipe.num_categories || 5}
          onChange={(e) => handleChange('num_categories', parseInt(e.target.value) || 5)}
          className="mt-1"
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of category metadata keys to generate (1-20)
        </p>
      </div>

      <div>
        <Label htmlFor="num_topics">Number of Consumer Topics</Label>
        <Input
          id="num_topics"
          type="number"
          min="1"
          max="30"
          value={recipe.num_topics || 8}
          onChange={(e) => handleChange('num_topics', parseInt(e.target.value) || 8)}
          className="mt-1"
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of consumer topics that reference metadata keys (1-30)
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="pretty_print"
          checked={recipe.pretty_print !== false}
          onCheckedChange={(checked) => handleChange('pretty_print', checked)}
        />
        <Label htmlFor="pretty_print" className="cursor-pointer">
          Pretty Print XML
        </Label>
      </div>
      <p className="text-sm text-gray-500">
        Format XML output with indentation for readability
      </p>

      <div className="mt-4 p-4 bg-blue-50 rounded-lg">
        <h4 className="font-semibold text-sm mb-2">About Keyword Metadata Key Map</h4>
        <p className="text-sm text-gray-700">
          This dataset demonstrates DITA keyword metadata key resolution:
        </p>
        <ul className="text-sm text-gray-700 mt-2 list-disc list-inside space-y-1">
          <li>Metadata map defines keys for keywords, categories, and tags</li>
          <li>Keyword/metadata topics contain the actual metadata definitions</li>
          <li>Consumer topics use keyrefs to reference metadata keys</li>
          <li>Metadata map uses processing-role="resource-only" to make keys available without including topics in navigation</li>
        </ul>
        <p className="text-sm text-gray-700 mt-2">
          All IDs are DITA-compliant (start with letter/underscore, no leading digits).
        </p>
      </div>
    </div>
  );
}
