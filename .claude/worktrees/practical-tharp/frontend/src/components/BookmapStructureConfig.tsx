import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';

interface BookmapStructureConfigProps {
  recipe: {
    chapter_count?: number;
    topics_per_chapter?: number;
    include_frontmatter?: boolean;
    include_backmatter?: boolean;
    pretty_print?: boolean;
  };
  onChange: (recipe: any) => void;
}

export function BookmapStructureConfig({ recipe, onChange }: BookmapStructureConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <Label>Chapter Count</Label>
        <Input
          type="number"
          value={recipe.chapter_count || 10}
          onChange={(e) => onChange({
            type: 'bookmap_structure',
            chapter_count: parseInt(e.target.value) || 10,
            topics_per_chapter: recipe.topics_per_chapter ?? 5,
            include_frontmatter: recipe.include_frontmatter ?? true,
            include_backmatter: recipe.include_backmatter ?? true,
            pretty_print: recipe.pretty_print ?? true,
          })}
          min={1}
          max={100}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of chapters in the bookmap
        </p>
      </div>

      <div>
        <Label>Topics per Chapter</Label>
        <Input
          type="number"
          value={recipe.topics_per_chapter || 5}
          onChange={(e) => onChange({
            type: 'bookmap_structure',
            chapter_count: recipe.chapter_count ?? 10,
            topics_per_chapter: parseInt(e.target.value) || 5,
            include_frontmatter: recipe.include_frontmatter ?? true,
            include_backmatter: recipe.include_backmatter ?? true,
            pretty_print: recipe.pretty_print ?? true,
          })}
          min={1}
          max={50}
        />
        <p className="text-sm text-gray-500 mt-1">
          Number of topics in each chapter
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-frontmatter"
          checked={recipe.include_frontmatter !== false}
          onCheckedChange={(checked) => onChange({
            type: 'bookmap_structure',
            chapter_count: recipe.chapter_count ?? 10,
            topics_per_chapter: recipe.topics_per_chapter ?? 5,
            include_frontmatter: checked,
            include_backmatter: recipe.include_backmatter ?? true,
            pretty_print: recipe.pretty_print ?? true,
          })}
        />
        <Label htmlFor="include-frontmatter">Include Frontmatter</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="include-backmatter"
          checked={recipe.include_backmatter !== false}
          onCheckedChange={(checked) => onChange({
            type: 'bookmap_structure',
            chapter_count: recipe.chapter_count ?? 10,
            topics_per_chapter: recipe.topics_per_chapter ?? 5,
            include_frontmatter: recipe.include_frontmatter ?? true,
            include_backmatter: checked,
            pretty_print: recipe.pretty_print ?? true,
          })}
        />
        <Label htmlFor="include-backmatter">Include Backmatter</Label>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="pretty-print"
          checked={recipe.pretty_print !== false}
          onCheckedChange={(checked) => onChange({
            type: 'bookmap_structure',
            chapter_count: recipe.chapter_count ?? 10,
            topics_per_chapter: recipe.topics_per_chapter ?? 5,
            include_frontmatter: recipe.include_frontmatter ?? true,
            include_backmatter: recipe.include_backmatter ?? true,
            pretty_print: checked,
          })}
        />
        <Label htmlFor="pretty-print">Pretty Print XML</Label>
      </div>
    </div>
  );
}
