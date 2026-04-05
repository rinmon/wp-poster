<?php
/**
 * 高速タイトル重複チェック用 カスタムAPIエンドポイント
 * 
 * お使いのテーマの functions.php または Code Snippets プラグイン等に追加してください。
 * タイトル完全一致でデータベースを直接検索するため、標準API(search=)の全文検索より圧倒的に高速です。
 * 
 * アクセスURL: GET /wp-json/custom/v1/check-title?title=...
 */
add_action('rest_api_init', function () {
    register_rest_route('custom/v1', '/check-title', array(
        'methods' => 'GET',
        'callback' => 'custom_api_check_title_exists',
        'permission_callback' => function () {
            // セキュリティのため、投稿編集権限を持つユーザー（Application Passwords等で認証済）のみアクセス可
            return current_user_can('edit_posts');
        }
    ));
});

function custom_api_check_title_exists($request) {
    global $wpdb;
    
    $title = $request->get_param('title');
    if (empty($title)) {
        return new WP_REST_Response(array('exists' => false), 200);
    }
    
    // publish, future, draft, private の中からタイトルが完全一致する記事を1件だけ検索
    $query = $wpdb->prepare(
        "SELECT ID FROM {$wpdb->posts} WHERE post_title = %s AND post_status IN ('publish', 'future', 'draft', 'private') AND post_type = 'post' LIMIT 1",
        $title
    );
    
    $post_id = $wpdb->get_var($query);
    
    if ($post_id) {
        return new WP_REST_Response(array('exists' => true, 'id' => (int)$post_id), 200);
    } else {
        return new WP_REST_Response(array('exists' => false), 200);
    }
}
