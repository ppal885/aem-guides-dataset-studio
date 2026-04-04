import { useCallback, useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { useAppFeedback } from './feedback/useAppFeedback';
import { Star, Share2, Trash2, Plus } from 'lucide-react';
import { useRequestCancellationWithDeps } from '@/hooks/useRequestCancellation';

interface SavedRecipe {
  id: string;
  name: string;
  description: string | null;
  is_public: boolean;
  tags: string[];
  usage_count: number;
  created_at: string;
  is_owner: boolean;
}

interface RecipeLibraryProps {
  onSelectRecipe: (recipeId: string) => void;
  onSaveRecipe?: (name: string, description: string, recipeConfig: any, isPublic: boolean, tags: string[]) => void;
}

export function RecipeLibrary({ onSelectRecipe, onSaveRecipe }: RecipeLibraryProps) {
  const feedback = useAppFeedback();
  const [recipes, setRecipes] = useState<SavedRecipe[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const isMountedRef = useRef(true);
  const abortController = useRequestCancellationWithDeps([searchQuery, selectedTags]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const loadRecipes = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append('search', searchQuery);
      if (selectedTags.length > 0) params.append('tags', selectedTags.join(','));
      
      const response = await fetch(`/api/v1/recipes?${params.toString()}`, {
        signal: abortController.signal,
      });
      
      if (abortController.signal.aborted || !isMountedRef.current) {
        return;
      }
      
      if (response.ok) {
        const data = await response.json();
        if (!abortController.signal.aborted && isMountedRef.current) {
          setRecipes(data.recipes || []);
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return;
      }
      if (isMountedRef.current) {
        console.error('Failed to load recipes:', error);
      }
    } finally {
      if (isMountedRef.current && !abortController.signal.aborted) {
        setLoading(false);
      }
    }
  }, [abortController.signal, searchQuery, selectedTags]);

  useEffect(() => {
    void loadRecipes();
  }, [loadRecipes]);

  const handleUseRecipe = async (recipeId: string) => {
    try {
      const response = await fetch(`/api/v1/recipes/${recipeId}/use`, {
        method: 'POST',
      });
      if (response.ok) {
        await response.json();
        onSelectRecipe(recipeId);
        // Reload to update usage count
        loadRecipes();
      }
    } catch (error) {
      console.error('Failed to use recipe:', error);
    }
  };

  const handleDeleteRecipe = async (recipeId: string) => {
    const confirmed = await feedback.confirm({
      title: 'Delete saved recipe?',
      message: 'This removes the recipe from your library. This action cannot be undone.',
      confirmLabel: 'Delete recipe',
      tone: 'danger',
    });
    if (!confirmed) return;
    
    try {
      const response = await fetch(`/api/v1/recipes/${recipeId}`, {
        method: 'DELETE',
      });
      if (response.ok) {
        loadRecipes();
      } else {
        feedback.error('Failed to delete recipe', 'The recipe could not be deleted.');
      }
    } catch (error) {
      console.error('Failed to delete recipe:', error);
      feedback.error('Failed to delete recipe', 'The recipe could not be deleted.');
    }
  };

  const allTags = Array.from(new Set(recipes.flatMap(r => r.tags)));

  if (loading) {
    return <div className="text-center py-4">Loading recipe library...</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Recipe Library</h3>
        {onSaveRecipe && (
          <Button onClick={() => setShowSaveDialog(true)} size="sm">
            <Plus className="h-4 w-4 mr-2" />
            Save Recipe
          </Button>
        )}
      </div>

      {/* Search and Filters */}
      <div className="space-y-2">
        <Input
          placeholder="Search recipes..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        
        {allTags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {allTags.map(tag => (
              <Badge
                key={tag}
                variant={selectedTags.includes(tag) ? "default" : "outline"}
                className="cursor-pointer"
                onClick={() => {
                  setSelectedTags(prev =>
                    prev.includes(tag)
                      ? prev.filter(t => t !== tag)
                      : [...prev, tag]
                  );
                }}
              >
                {tag}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Recipe Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {recipes.map(recipe => (
          <Card key={recipe.id} className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <CardTitle className="text-base">{recipe.name}</CardTitle>
                  {recipe.description && (
                    <CardDescription className="text-sm mt-1">
                      {recipe.description}
                    </CardDescription>
                  )}
                </div>
                {recipe.is_public && (
                  <Share2 className="h-4 w-4 text-blue-500" />
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* Tags */}
              {recipe.tags.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {recipe.tags.map(tag => (
                    <Badge key={tag} variant="outline" className="text-xs">
                      {tag}
                    </Badge>
                  ))}
                </div>
              )}

              {/* Stats */}
              <div className="flex items-center gap-4 text-sm text-gray-500">
                <div className="flex items-center gap-1">
                  <Star className="h-3 w-3" />
                  <span>{recipe.usage_count} uses</span>
                </div>
                {recipe.is_owner && (
                  <span className="text-xs">Your recipe</span>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-2">
                <Button
                  onClick={() => handleUseRecipe(recipe.id)}
                  className="flex-1"
                  size="sm"
                >
                  Use Recipe
                </Button>
                {recipe.is_owner && (
                  <>
                    <Button
                      onClick={() => handleDeleteRecipe(recipe.id)}
                      variant="outline"
                      size="sm"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {recipes.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          No recipes found. {onSaveRecipe && "Save a recipe to get started!"}
        </div>
      )}

      {/* Save Dialog would go here */}
      {showSaveDialog && onSaveRecipe && (
        <SaveRecipeDialog
          onSave={onSaveRecipe}
          onClose={() => setShowSaveDialog(false)}
        />
      )}
    </div>
  );
}

function SaveRecipeDialog({
  onSave,
  onClose,
}: {
  onSave: (name: string, description: string, recipeConfig: any, isPublic: boolean, tags: string[]) => void;
  onClose: () => void;
}) {
  const feedback = useAppFeedback();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [tags, setTags] = useState('');

  const handleSave = () => {
    if (!name.trim()) {
      feedback.warning('Recipe name required', 'Please enter a recipe name before saving.');
      return;
    }
    // This would get the current recipe config from parent
    // For now, we'll use a placeholder
    onSave(name, description, {}, isPublic, tags.split(',').map(t => t.trim()).filter(Boolean));
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Save Recipe</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Name</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Recipe name"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Description</label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Tags (comma-separated)</label>
            <Input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="performance, test, large"
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="public"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            <label htmlFor="public" className="text-sm">Make public (share with others)</label>
          </div>
          <div className="flex gap-2">
            <Button onClick={handleSave} className="flex-1">Save</Button>
            <Button onClick={onClose} variant="outline">Cancel</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
