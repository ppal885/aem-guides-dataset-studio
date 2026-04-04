import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface ConceptTopicsConfigProps {
  recipe: {
    topic_count?: number;
    sections_per_concept?: number;
    include_map?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function ConceptTopicsConfig({ recipe, onChange }: ConceptTopicsConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>Topic Count</Label>
        <Input
          type="number"
          value={recipe.topic_count || 50}
          onChange={(e) => onChange({
            type: 'concept_topics',
            topic_count: parseInt(e.target.value) || 50,
            sections_per_concept: recipe.sections_per_concept ?? 3,
            include_map: recipe.include_map ?? true,
            pretty_print: recipe.pretty_print ?? true,
          })}
          min={10}
          max={5000}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of Concept topics to generate
        </p>
      </div>

      <div>
        <Label>Sections per Concept</Label>
        <Input
          type="number"
          value={recipe.sections_per_concept || 3}
          onChange={(e) => onChange({
            type: 'concept_topics',
            topic_count: recipe.topic_count ?? 50,
            sections_per_concept: parseInt(e.target.value) || 3,
            include_map: recipe.include_map ?? true,
            pretty_print: recipe.pretty_print ?? true,
          })}
          min={1}
          max={10}
        />
        <p className="text-sm text-gray-500 mt-1">
          Average number of sections in each concept topic
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-map"
          checked={recipe.include_map !== false}
          onCheckedChange={(checked) => onChange({
            type: 'concept_topics',
            topic_count: recipe.topic_count ?? 50,
            sections_per_concept: recipe.sections_per_concept ?? 3,
            include_map: checked,
            pretty_print: recipe.pretty_print ?? true,
          })}
        />
        <Label htmlFor="include-map">Include Map</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="pretty-print"
          checked={recipe.pretty_print !== false}
          onCheckedChange={(checked) => onChange({
            type: 'concept_topics',
            topic_count: recipe.topic_count ?? 50,
            sections_per_concept: recipe.sections_per_concept ?? 3,
            include_map: recipe.include_map ?? true,
            pretty_print: checked,
          })}
        />
        <Label htmlFor="pretty-print">Pretty Print XML</Label>
      </div>
    </div>
  );
}
