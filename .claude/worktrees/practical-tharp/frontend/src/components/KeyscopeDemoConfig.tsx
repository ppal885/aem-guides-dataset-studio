import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface KeyscopeDemoConfigProps {
  recipe: {
    id_prefix?: string;
    include_qualified_keyrefs?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function KeyscopeDemoConfig({ recipe, onChange }: KeyscopeDemoConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>ID Prefix</Label>
        <Input
          type="text"
          value={recipe.id_prefix || 't'}
          onChange={(e) => {
            const value = e.target.value;
            if (!value || (value[0] && (value[0].match(/[A-Za-z_]/)))) {
              onChange({ ...recipe, id_prefix: value || 't' });
            }
          }}
          placeholder="t"
          pattern="[A-Za-z_][-A-Za-z0-9_.]*"
        />
        <p className="text-sm text-gray-500 mt-1">
          Prefix for generated IDs (must start with letter or underscore). Default: "t"
        </p>
        {recipe.id_prefix && recipe.id_prefix[0] && recipe.id_prefix[0].match(/[0-9]/) && (
          <p className="text-sm text-red-500 mt-1">
            ID prefix must start with a letter or underscore
          </p>
        )}
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-qualified-keyrefs"
          checked={recipe.include_qualified_keyrefs !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, include_qualified_keyrefs: checked })}
        />
        <Label htmlFor="include-qualified-keyrefs" className="cursor-pointer">
          Include Qualified Keyrefs
        </Label>
      </div>
      <p className="text-sm text-gray-500">
        Include explicit qualified keyrefs (s1.prod, s2.prod) for diagnostics
      </p>

      <div className="flex items-center space-x-2">
        <Switch
          id="pretty-print"
          checked={recipe.pretty_print !== false}
          onCheckedChange={(checked) => onChange({ ...recipe, pretty_print: checked })}
        />
        <Label htmlFor="pretty-print" className="cursor-pointer">
          Pretty Print XML
        </Label>
      </div>
      <p className="text-sm text-gray-500">
        Format XML output with indentation for readability
      </p>

      <div className="mt-4 p-4 bg-blue-50 rounded-lg">
        <h4 className="font-semibold text-sm mb-2">About Keyscope Demo</h4>
        <p className="text-sm text-gray-700">
          This dataset demonstrates DITA keyscope resolution:
        </p>
        <ul className="text-sm text-gray-700 mt-2 list-disc list-inside space-y-1">
          <li>Root map defines key "prod" → root_target.dita</li>
          <li>Submap S1 defines key "prod" → s1_target.dita (keyscope="s1")</li>
          <li>Submap S2 defines key "prod" → s2_target.dita (keyscope="s2")</li>
          <li>Consumer topics use keyref="prod" with scoped resolution</li>
        </ul>
        <p className="text-sm text-gray-700 mt-2">
          All IDs are DITA-compliant (start with letter/underscore, no leading digits).
        </p>
      </div>
    </div>
  );
}
