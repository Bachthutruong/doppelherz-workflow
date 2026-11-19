<?php
/**
 * Plugin Name: Doppelherz Robot Webhook (mu-plugin)
 * Description: Khi một bài viết chuyển sang trạng thái "publish", gửi post_id tới n8n để robot tạo bản Facebook/Pinterest.
 * Cài đặt: chép file vào wp-content/mu-plugins/ và khai báo 2 hằng số trong wp-config.php:
 *   define('DH_ROBOT_WEBHOOK_URL', 'https://n8n.ten-mien-cua-ban.vn/webhook/doppelherz-new-post');
 *   define('DH_ROBOT_WEBHOOK_SECRET', 'chuoi-bi-mat');
 */
add_action('transition_post_status', function ($new_status, $old_status, $post) {
    if ($new_status !== 'publish' || $old_status === 'publish' || $post->post_type !== 'post') {
        return; // chỉ bài viết mới đăng lần đầu, bỏ qua lần cập nhật
    }
    if (!defined('DH_ROBOT_WEBHOOK_URL')) {
        return;
    }
    wp_remote_post(DH_ROBOT_WEBHOOK_URL, [
        'timeout'  => 5,
        'blocking' => false, // không làm chậm thao tác bấm "Đăng" của biên tập viên
        'headers'  => [
            'Content-Type'     => 'application/json',
            'X-Webhook-Secret' => defined('DH_ROBOT_WEBHOOK_SECRET') ? DH_ROBOT_WEBHOOK_SECRET : '',
        ],
        'body'     => wp_json_encode(['post_id' => $post->ID, 'url' => get_permalink($post)]),
    ]);
}, 10, 3);
